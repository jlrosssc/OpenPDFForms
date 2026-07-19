from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import secrets
import sqlite3
from pathlib import Path

from .storage import DATA_ROOT


AUTH_DB = DATA_ROOT / "auth.sqlite3"
SESSION_COOKIE = "openpdfforms_session"
SESSION_DAYS = 30
PBKDF2_ITERATIONS = 260_000


@dataclass(frozen=True)
class User:
    id: int
    username: str
    is_admin: bool
    active: bool


def _connect() -> sqlite3.Connection:
    AUTH_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTH_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_auth_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")


def users_exist() -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None


def _hash_password(password: str, salt: bytes | None = None) -> str:
    if not password:
        raise ValueError("Password is required.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _row_to_user(row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(id=int(row["id"]), username=str(row["username"]), is_admin=bool(row["is_admin"]), active=bool(row["active"]))


def create_user(username: str, password: str, *, is_admin: bool = False, active: bool = True) -> User:
    username = username.strip()
    if not username:
        raise ValueError("Username is required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, is_admin, active, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, _hash_password(password), int(is_admin), int(active), now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Username already exists.") from exc
        row = conn.execute("SELECT id, username, is_admin, active FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        user = _row_to_user(row)
        assert user is not None
        return user


def authenticate(username: str, password: str) -> User | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username.strip(),)).fetchone()
        if row is None or not _verify_password(password, row["password_hash"]):
            return None
        return _row_to_user(row)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=SESSION_DAYS)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, expires.isoformat(), now.isoformat()),
        )
    return token


def delete_session(token: str) -> None:
    if not token:
        return
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def user_from_session(token: str | None) -> User | None:
    if not token:
        return None
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT users.id, users.username, users.is_admin, users.active
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ? AND users.active = 1
            """,
            (token, now),
        ).fetchone()
        return _row_to_user(row)


def list_users() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT id, username, is_admin, active, created_at FROM users ORDER BY username COLLATE NOCASE").fetchall()
        return [dict(row) for row in rows]


def update_user(user_id: int, *, password: str | None = None, is_admin: bool | None = None, active: bool | None = None) -> User:
    assignments: list[str] = []
    values: list[object] = []
    if password:
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        assignments.append("password_hash = ?")
        values.append(_hash_password(password))
    if is_admin is not None:
        assignments.append("is_admin = ?")
        values.append(int(is_admin))
    if active is not None:
        assignments.append("active = ?")
        values.append(int(active))
    if assignments:
        values.append(user_id)
        with _connect() as conn:
            conn.execute(f"UPDATE users SET {', '.join(assignments)} WHERE id = ?", values)
            if active is False:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    with _connect() as conn:
        row = conn.execute("SELECT id, username, is_admin, active FROM users WHERE id = ?", (user_id,)).fetchone()
        user = _row_to_user(row)
        if user is None:
            raise ValueError("User not found.")
        return user


def delete_user(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
