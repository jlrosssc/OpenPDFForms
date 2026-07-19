# OpenPDFForms

OpenPDFForms is a local web app for turning flat, scanned, or existing AcroForm PDFs into editable fillable PDF forms. It is designed to work alongside Stirling PDF as a form-authoring companion: use Stirling for general PDF operations, then use OpenPDFForms when a PDF needs Acrobat-style form fields, scripting, fill/sign workflow, and verification.

## Current Capabilities

- Upload a PDF and render each page in the browser.
- Auto-detect likely text fields, checkboxes, and radio buttons. Detected and imported fields use short type-based names such as `text_1`, `checkbox_1`, or `radio_1`, while nearby or imported descriptive text is kept as the field label and tooltip.
- Import existing AcroForm fields from PDFs created in tools such as Adobe Acrobat.
- Add, move, resize, duplicate, align, distribute, or delete fields.
- Save and reopen editable OpenPDFForms projects.
- Export a fillable AcroForm PDF.
- Preview the PDF with current field values before export/signing.
- Fill forms in the browser and download the current signed/filled copy.
- Create typed or drawn signature appearances for Mock Sign fields.
- Apply E Sign fields with a cryptographic PDF signature backed by a local OpenPDFForms certificate authority.
- Download the local trust certificate so signatures can validate as trusted on managed machines.
- Customize detection and field naming with Python hooks.

## Field Types

OpenPDFForms supports these authoring field types:

- Text
- Date
- Checkbox
- Radio button groups
- Dropdown
- List box, including multi-select list boxes
- Button placeholder fields
- Mock Sign
- Initials
- E Sign / digital signature

## Field Properties

The Inspector supports common Acrobat-style field properties:

- Name, label, tooltip, type, page position, size, font size, max length
- Required, read-only, hidden, print/no-print, and do-not-export flags
- Default value
- Dropdown/list options
- Radio group name
- Multiline and comb text fields
- Multi-select list box behavior
- Text alignment
- Border style, border color, and background color
- Tab order
- Format presets: number, integer, percent, currency, date, ZIP code, and phone
- Calculations: sum, average, product, min, and max
- Visual conditional logic rules
- Advanced custom Acrobat JavaScript for format, validation, and calculation scripts

## Manual

### Create a Fillable Form

1. Open OpenPDFForms and upload a PDF.
2. Review the detected fields. Move, resize, rename, or delete anything that was detected incorrectly.
3. Add missing fields from the Add Field panel.
4. Select each field and use the Inspector to set its name, label, tooltip, required status, formatting, calculations, conditional logic, and visual style.
5. Use Preview to check the appearance with current field values.
6. Save Project if you want to keep editing later.
7. Export Fillable PDF when the form layout is ready.

### Fill and Sign

1. Open or upload a form project.
2. Choose Fill & Sign.
3. Fill visible fields in the browser.
4. Click a Mock Sign, Initials, or E Sign field to sign.
5. Required visible fields must be filled before signing.
6. Download Current Copy when the filled or signed copy is ready.

### E Sign Trust

OpenPDFForms generates a local root certificate and local signing identity on first use. Download the Trust Certificate from the toolbar and install it only on machines that should trust signatures produced by that OpenPDFForms instance.

The local certificate authority is useful for private/internal workflows. Publicly trusted or regulated signing workflows should use organization-managed certificates, hardware-backed keys, timestamp authority support, and formal identity proofing. Those are roadmap items rather than a claim of current Adobe Sign equivalence.

### Custom Scripts

The Custom Script section accepts Acrobat JavaScript snippets for format, validation, and calculation events. These scripts run only in PDF viewers that execute Acrobat JavaScript, such as Adobe Acrobat/Reader. Viewers without PDF JavaScript support will still show the form fields, but scripted behavior may not run.

### Python Hooks

Copy `hooks.example.py` to `hooks.py` and edit `process_fields()` to rename, filter, or adjust detected fields before they appear in the editor.

## Built-in Access Control

OpenPDFForms includes app-level login and admin user management. On a new install, visit the app and create the first administrator account on the setup page. After signing in, admins can open **Users** from the top toolbar to add users, disable users, reset passwords, and grant or remove admin access.

If OpenPDFForms is deployed behind Apache, nginx, or `.htaccess` basic authentication, keep the external protection in place until the first app admin account has been created and verified. After that, the proxy-level password can be removed if you want access controlled by OpenPDFForms itself.

## Stirling PDF Integration

The deployment files can run OpenPDFForms beside Stirling PDF behind a reverse proxy. The intended workflow is:

- Use Stirling PDF for general PDF operations.
- Send PDFs that need form authoring to OpenPDFForms.
- Export the fillable PDF from OpenPDFForms.
- Return to Stirling PDF for any additional merge, split, compression, or organization tasks.

A deeper Stirling integration should add a direct Create Fillable Form action, shared file handoff, shared authentication, and return-to-Stirling behavior after export.

## Roadmap Toward Adobe-Style Parity

High-value next features:

- PKCS#12/PFX signing certificate import with encrypted private-key storage.
- Timestamp authority support and long-term validation data for signed PDFs.
- Signature status display, audit trail, and signer identity metadata.
- FDF, XFDF, CSV, and JSON import/export for form data.
- Submit buttons, webhooks, email submission, and response tracking.
- OCR-assisted detection for scanned PDFs, deskew/cleanup, and confidence scoring.
- Better radio/checkbox grouping and field-name suggestions.
- Accessibility checks: tab order, reading order, screen-reader labels, and PDF/UA warnings.
- Document-level JavaScript and more Acrobat event hooks.
- XFA detection with a clear warning and possible conversion/import support later.

## Quick Start

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn openpdfforms.app:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Notes

This is intentionally local-first. Uploaded PDFs are stored in `data/uploads`, rendered page images in `data/renders`, exported PDFs in `data/exports`, saved projects in `data/projects`, working filled/signed PDFs in `data/working`, and signing material in `data/signing`.

The detector is heuristic-based. It uses PDF text geometry and page rendering analysis to find likely fields, then expects a human to review the overlay before export.

OpenPDFForms separates the editable project from the distributable PDF:

- **Save Project** stores the original PDF plus edited field layout under `data/projects`.
- **Open Project** reopens the editable overlay later.
- **Export Fillable PDF** creates the PDF you can distribute to other people.
- **Fill & Sign** creates a working filled/signed copy.

## License

OpenPDFForms is licensed under AGPL-3.0-or-later (see `LICENSE`).

This project uses PyMuPDF under its free AGPL-3.0-or-later license. If you make OpenPDFForms or a modified version available to other users over a network, AGPL-3.0 requires that those users can access the corresponding source code for the version they are using. The bundled web interface includes a **Source** link for this purpose.

If you cannot satisfy AGPL-3.0 obligations for your use case, obtain a commercial PyMuPDF license from Artifex before deploying the app.

## Third-Party Licenses

This project depends on several third-party libraries, including PyMuPDF under AGPL-3.0-or-later. See `THIRD_PARTY_LICENSES.md` for the full list and what AGPL-3.0 requires if you host a modified version of this app.
