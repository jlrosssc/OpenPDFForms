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
    idle_timeout_minutes: int = 0
    session_lifetime_days: int = SESSION_DAYS
    expire_on_browser_close: bool = False


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
        _ensure_column(conn, "users", "idle_timeout_minutes", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "users", "session_lifetime_days", f"INTEGER NOT NULL DEFAULT {SESSION_DAYS}")
        _ensure_column(conn, "users", "expire_on_browser_close", "INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        _ensure_column(conn, "sessions", "last_seen_at", "TEXT NOT NULL DEFAULT ''")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE sessions SET last_seen_at = created_at WHERE last_seen_at = ''")
        conn.execute("UPDATE sessions SET last_seen_at = ? WHERE last_seen_at = ''", (now,))
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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
    keys = set(row.keys())
    return User(
        id=int(row["id"]),
        username=str(row["username"]),
        is_admin=bool(row["is_admin"]),
        active=bool(row["active"]),
        idle_timeout_minutes=int(row["idle_timeout_minutes"]) if "idle_timeout_minutes" in keys else 0,
        session_lifetime_days=int(row["session_lifetime_days"]) if "session_lifetime_days" in keys else SESSION_DAYS,
        expire_on_browser_close=bool(row["expire_on_browser_close"]) if "expire_on_browser_close" in keys else False,
    )


def create_user(
    username: str,
    password: str,
    *,
    is_admin: bool = False,
    active: bool = True,
    idle_timeout_minutes: int = 0,
    session_lifetime_days: int = SESSION_DAYS,
    expire_on_browser_close: bool = False,
) -> User:
    username = username.strip()
    if not username:
        raise ValueError("Username is required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (
                    username, password_hash, is_admin, active, idle_timeout_minutes,
                    session_lifetime_days, expire_on_browser_close, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    _hash_password(password),
                    int(is_admin),
                    int(active),
                    max(0, int(idle_timeout_minutes)),
                    max(1, int(session_lifetime_days)),
                    int(expire_on_browser_close),
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Username already exists.") from exc
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        user = _row_to_user(row)
        assert user is not None
        return user


def authenticate(username: str, password: str) -> User | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username.strip(),)).fetchone()
        if row is None or not _verify_password(password, row["password_hash"]):
            return None
        return _row_to_user(row)


def create_session(user_id: int) -> tuple[str, int | None]:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        user = _row_to_user(row)
        if user is None:
            raise ValueError("User not found.")
        lifetime_days = max(1, user.session_lifetime_days)
        expires = now + timedelta(days=lifetime_days)
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at, last_seen_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (token, user_id, expires.isoformat(), now.isoformat(), now.isoformat()),
        )
    return token, None if user.expire_on_browser_close else lifetime_days * 24 * 60 * 60


def delete_session(token: str) -> None:
    if not token:
        return
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def user_from_session(token: str | None) -> User | None:
    if not token:
        return None
    now = datetime.now(timezone.utc)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT users.*, sessions.last_seen_at, sessions.expires_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ? AND users.active = 1
            """,
            (token, now.isoformat()),
        ).fetchone()
        user = _row_to_user(row)
        if user is None:
            return None
        if user.idle_timeout_minutes > 0:
            try:
                last_seen = datetime.fromisoformat(str(row["last_seen_at"]))
            except ValueError:
                last_seen = now
            if now - last_seen > timedelta(minutes=user.idle_timeout_minutes):
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None
        conn.execute("UPDATE sessions SET last_seen_at = ? WHERE token = ?", (now.isoformat(), token))
        return user


def list_users() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, username, is_admin, active, created_at, idle_timeout_minutes,
                   session_lifetime_days, expire_on_browser_close
            FROM users
            ORDER BY username COLLATE NOCASE
            """
        ).fetchall()
        return [dict(row) for row in rows]


def update_user(
    user_id: int,
    *,
    password: str | None = None,
    is_admin: bool | None = None,
    active: bool | None = None,
    idle_timeout_minutes: int | None = None,
    session_lifetime_days: int | None = None,
    expire_on_browser_close: bool | None = None,
) -> User:
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
    if idle_timeout_minutes is not None:
        assignments.append("idle_timeout_minutes = ?")
        values.append(max(0, int(idle_timeout_minutes)))
    if session_lifetime_days is not None:
        assignments.append("session_lifetime_days = ?")
        values.append(max(1, int(session_lifetime_days)))
    if expire_on_browser_close is not None:
        assignments.append("expire_on_browser_close = ?")
        values.append(int(expire_on_browser_close))
    if assignments:
        values.append(user_id)
        with _connect() as conn:
            conn.execute(f"UPDATE users SET {', '.join(assignments)} WHERE id = ?", values)
            if active is False:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        user = _row_to_user(row)
        if user is None:
            raise ValueError("User not found.")
        return user


def delete_user(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
