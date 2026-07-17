from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata

from .storage import SIGNING_ROOT

CERT_PATH = SIGNING_ROOT / "cert.pem"
KEY_PATH = SIGNING_ROOT / "key.pem"


def ensure_signing_identity(common_name: str = "OpenPDFForms Local Signer") -> tuple[Path, Path]:
    """Return (cert_path, key_path), generating a self-signed identity on first use.

    This is a self-signed certificate: PDF viewers will show the signature as
    cryptographically valid (tamper-evident) but not as coming from a trusted
    authority. Swap in a real CA-issued Digital ID by replacing these two files
    to get a trusted signature instead.
    """
    SIGNING_ROOT.mkdir(parents=True, exist_ok=True)
    if CERT_PATH.exists() and KEY_PATH.exists():
        return CERT_PATH, KEY_PATH

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    KEY_PATH.chmod(0o600)
    return CERT_PATH, KEY_PATH


def sign_pdf(
    input_pdf: Path,
    output_pdf: Path,
    *,
    signer_name: str = "",
    reason: str = "",
    location: str = "",
) -> None:
    """Apply a PAdES-style cryptographic signature to input_pdf, writing output_pdf."""
    cert_path, key_path = ensure_signing_identity()
    signer = signers.SimpleSigner.load(
        key_file=str(key_path),
        cert_file=str(cert_path),
        key_passphrase=None,
    )

    meta = PdfSignatureMetadata(
        field_name="DigitalSignature1",
        reason=reason or None,
        location=location or None,
        name=signer_name or None,
    )

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with input_pdf.open("rb") as inf, output_pdf.open("wb") as outf:
        writer = IncrementalPdfFileWriter(inf)
        signers.sign_pdf(writer, meta, signer=signer, output=outf)
