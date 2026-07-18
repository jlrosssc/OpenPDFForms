from __future__ import annotations

import base64
import io
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PIL import Image
from pyhanko import stamp
from pyhanko.pdf_utils.images import PdfImage
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import signers
from pyhanko.sign.fields import MDPPerm
from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata

from .models import FieldType, FormField
from .storage import SIGNING_ROOT

CA_CERT_PATH = SIGNING_ROOT / "ca-cert.pem"
CA_KEY_PATH = SIGNING_ROOT / "ca-key.pem"
CERT_PATH = SIGNING_ROOT / "cert.pem"
KEY_PATH = SIGNING_ROOT / "key.pem"


def ensure_root_ca(common_name: str = "OpenPDFForms Root CA") -> tuple[Path, Path]:
    """Return (ca_cert_path, ca_key_path), generating a self-signed root CA on first use.

    This root is the trust anchor: its private key never leaves the server,
    and its public certificate is the one artifact an organization installs
    on its own machines (as a trusted root) so E Sign signatures validate as
    trusted rather than merely tamper-evident. See ensure_signing_identity()
    for the leaf certificate issued from this root.
    """
    SIGNING_ROOT.mkdir(parents=True, exist_ok=True)
    if CA_CERT_PATH.exists() and CA_KEY_PATH.exists():
        return CA_CERT_PATH, CA_KEY_PATH

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
        .not_valid_after(now + timedelta(days=3650 * 2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )

    CA_KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CA_CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    CA_KEY_PATH.chmod(0o600)
    return CA_CERT_PATH, CA_KEY_PATH


def ensure_signing_identity(common_name: str = "OpenPDFForms Local Signer") -> tuple[Path, Path]:
    """Return (cert_path, key_path): a leaf signing cert issued by the local root CA.

    Chaining to the root CA (instead of self-signing the leaf) is what lets
    the signature validate as fully trusted once the CA's public
    certificate is installed as a trusted root -- see ensure_root_ca().
    """
    SIGNING_ROOT.mkdir(parents=True, exist_ok=True)
    if CERT_PATH.exists() and KEY_PATH.exists():
        return CERT_PATH, KEY_PATH

    ca_cert_path, ca_key_path = ensure_root_ca()
    ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
    ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_cert.subject)
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
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
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


def has_existing_signature(pdf_path: Path) -> bool:
    with pdf_path.open("rb") as f:
        return len(PdfFileReader(f).embedded_signatures) > 0


def _escape_pdf_string(value: str) -> str:
    return value.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _font_size_from_da(da: str) -> float:
    match = re.search(r"([\d.]+)\s+Tf", da or "")
    return float(match.group(1)) if match else 10.0


def _rewrite_text_appearance(doc: fitz.Document, widget: "fitz.Widget", value: str) -> None:
    """Regenerate a text widget's appearance stream to actually show `value`.

    Setting /V alone doesn't repaint anything -- viewers render from the
    /AP appearance stream, not the raw value. Rewriting *only* the stream
    body (via update_stream, keeping the XObject's dict/BBox/Resources
    untouched) is critical: calling PyMuPDF's own Widget.update() instead
    was verified to touch an unrelated annotation's border width as a side
    effect, which pyHanko's diff analysis flags as a suspicious
    modification -- turning a legitimate fill into a DocMDP violation.
    """
    ap_entry = doc.xref_get_key(widget.xref, "AP/N")
    if ap_entry[0] != "xref":
        return
    ap_xref = int(ap_entry[1].split()[0])
    ap_dict = doc.xref_object(ap_xref)
    bbox_match = re.search(r"/BBox\s*\[\s*([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s*\]", ap_dict)
    box_height = float(bbox_match.group(4)) - float(bbox_match.group(2)) if bbox_match else widget.rect.height

    da = doc.xref_get_key(widget.xref, "DA")[1] or "0 0 0 rg /Helv 10 Tf"
    font_size = _font_size_from_da(da)
    baseline_y = max(2.0, (box_height - font_size) / 2 + font_size * 0.2)

    escaped = _escape_pdf_string(value)
    content = f"/Tx BMC\nq\nBT\n{da}\n2 {baseline_y:.2f} Td\n({escaped}) Tj\nET\nQ\nEMC\n"
    doc.update_stream(ap_xref, content.encode("latin-1", errors="replace"))


def apply_field_values(input_pdf: Path, output_pdf: Path, fields: list[FormField]) -> None:
    """Write current field values into input_pdf via minimal, DocMDP-safe edits.

    Sets /V (and /AS for checkboxes/radios) directly on each widget's xref
    and, for text-like fields, regenerates just the appearance stream body
    so the value is actually visible -- see _rewrite_text_appearance for
    why that has to be done surgically rather than via widget.update().

    Always saves incrementally (copying first if output_pdf differs from
    input_pdf) so any signatures already present in input_pdf stay valid --
    a full non-incremental rewrite invalidates prior signatures entirely.
    """
    if output_pdf != input_pdf:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(input_pdf, output_pdf)

    doc = fitz.open(output_pdf)
    by_name = {}
    for page in doc:
        for widget in page.widgets():
            by_name.setdefault(widget.field_name, []).append(widget)

    for field in fields:
        widgets = by_name.get(field.name)
        if not widgets:
            continue
        if field.type == FieldType.checkbox:
            state = "/Yes" if field.value in ("Yes", "true", "True", "1") else "/Off"
            for widget in widgets:
                doc.xref_set_key(widget.xref, "V", state)
                doc.xref_set_key(widget.xref, "AS", state)
        elif field.type == FieldType.radio:
            if not field.value:
                continue
            state = "/Yes" if field.value in ("Yes", "true", "True", "1") else "/Off"
            for widget in widgets:
                doc.xref_set_key(widget.xref, "V", state)
                doc.xref_set_key(widget.xref, "AS", state)
        elif field.type in (FieldType.signature, FieldType.digital_signature):
            continue
        else:
            if not field.value:
                continue
            escaped = f"({_escape_pdf_string(field.value)})"
            for widget in widgets:
                doc.xref_set_key(widget.xref, "V", escaped)
                _rewrite_text_appearance(doc, widget, field.value)

    doc.saveIncr()
    doc.close()


def sign_field(
    input_pdf: Path,
    output_pdf: Path,
    *,
    field_name: str,
    kind: str,
    signer_name: str = "",
    reason: str = "",
    location: str = "",
    signature_image_data_url: str = "",
) -> None:
    """Cryptographically sign one existing, empty signature field in-place.

    kind: "mock" renders the signer's name as a script-font image stamp
    (Mock Sign); "esign" renders a text stamp with signer/date/reason/
    location (E Sign). Both use the same underlying certificate and
    locking mechanism -- they differ only in visual presentation.

    The first signature applied to a document certifies it with
    MDPPerm.FILL_FORMS (locks against arbitrary edits, but still allows
    filling remaining fields and adding further signatures) so a form
    with multiple signature lines -- e.g. Manager / VP / SVP -- can be
    signed by different people at different times. Later signatures are
    plain approval signatures layered on top via further incremental
    updates.
    """
    ca_cert_path, _ = ensure_root_ca()
    cert_path, key_path = ensure_signing_identity()
    signer = signers.SimpleSigner.load(
        key_file=str(key_path),
        cert_file=str(cert_path),
        ca_chain_files=(str(ca_cert_path),),
        key_passphrase=None,
    )

    already_signed = has_existing_signature(input_pdf)

    text_params = None
    if kind == "mock" and signature_image_data_url and "base64," in signature_image_data_url:
        image_bytes = base64.b64decode(signature_image_data_url.split("base64,", 1)[1])
        pil_image = Image.open(io.BytesIO(image_bytes))
        stamp_style = stamp.StaticStampStyle(background=PdfImage(pil_image), border_width=0)
    else:
        lines = ["Digitally signed"]
        if signer_name:
            lines.append("by %(signer)s")
        lines.append("%(ts)s")
        if reason:
            lines.append("Reason: %(reason)s")
        if location:
            lines.append("Location: %(location)s")
        stamp_style = stamp.TextStampStyle(stamp_text="\n".join(lines), border_width=1)
        text_params = {"signer": signer_name, "reason": reason, "location": location}

    meta_kwargs = dict(
        field_name=field_name,
        reason=reason or None,
        location=location or None,
        name=signer_name or None,
    )
    if not already_signed:
        meta_kwargs["certify"] = True
        meta_kwargs["docmdp_permissions"] = MDPPerm.FILL_FORMS
    meta = PdfSignatureMetadata(**meta_kwargs)
    pdf_signer = signers.PdfSigner(meta, signer, stamp_style=stamp_style)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with input_pdf.open("rb") as inf, output_pdf.open("wb") as outf:
        writer = IncrementalPdfFileWriter(inf)
        pdf_signer.sign_pdf(
            writer,
            existing_fields_only=True,
            output=outf,
            appearance_text_params=text_params,
        )
