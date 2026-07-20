# OpenPDFForms

OpenPDFForms is a local web app for turning flat, scanned, or existing AcroForm PDFs into editable fillable PDF forms. It is designed to work alongside Stirling PDF as a form-authoring companion: use Stirling for general PDF operations, then use OpenPDFForms when a PDF needs Acrobat-style form fields, scripting, fill/sign workflow, and verification.

## Current Capabilities

- Upload a PDF, image, or common office document; non-PDF uploads are converted to PDF before rendering and field detection.
- Create a new blank PDF form from scratch using Letter, Legal, or A4 pages in portrait or landscape orientation.
- Auto-detect likely text fields, checkboxes, and radio buttons. Detected and imported fields use short type-based names such as `text_1`, `checkbox_1`, or `radio_1`, while nearby or imported descriptive text is kept as the field label and tooltip.
- Import existing AcroForm fields from PDFs created in tools such as Adobe Acrobat.
- Add, move, resize, duplicate, align, distribute, or delete fields.
- Add static base-document edits such as printed text, whiteout rectangles, and images.
- Save and reopen editable OpenPDFForms projects.
- Export a fillable AcroForm PDF.
- Preview the PDF with current field values before export/signing.
- Fill forms in the browser and download the current signed/filled copy.
- Create typed or drawn signature appearances for Mock Sign fields.
- Apply E Sign fields with a cryptographic PDF signature backed by a local OpenPDFForms certificate authority.
- Download the local trust certificate so signatures can validate as trusted on managed machines.
- Manage app users with per-user idle timeout, remember duration, and browser-close logout settings.
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
- Static Text
- Whiteout
- Image

## Field Properties

The Inspector supports common Acrobat-style field properties:

- Name, label, tooltip, type, page position, size, font size, max length
- Required, read-only, hidden, print/no-print, and do-not-export flags
- Default value
- Auto-fit text for fields where entered text may be longer than the visible box
- Dropdown/list options
- Radio group name
- Multiline and comb text fields
- Multi-select list box behavior
- Text alignment
- Border style, border color, and background color
- Tab order
- Format presets: number, integer, percent, currency, date, ZIP code, and phone
- Date/time auto-fill with selectable local date and date/time display formats
- Calculations: sum, average, product, min, and max
- Visual if / then / else conditional logic rules, with generated Acrobat JavaScript visible for review or reuse
- Button actions for clear form, print, submit form, reset current page, or custom Acrobat JavaScript
- Advanced custom Acrobat JavaScript for format, validation, and calculation scripts
- Built-in script test buttons for custom format, validation, calculation, and button-action scripts

## Manual

### Create a Fillable Form

1. Open OpenPDFForms and upload a PDF, image, Word/LibreOffice document, spreadsheet, presentation, text file, or CSV.
2. Review the detected fields. Move, resize, rename, or delete anything that was detected incorrectly.
3. Add missing fields from the Add Field panel.
4. Select each field and use the Inspector to set its name, label, tooltip, required status, formatting, calculations, conditional logic, and visual style.
5. Use Preview to check the appearance with current field values.
6. Save Project if you want to keep editing later.
7. Export Fillable PDF when the form layout is ready.

### Create a Form From Scratch

1. Click **New Blank Form**.
2. Choose filename, page size, orientation, and number of pages.
3. Add static text, images, whiteout, and fillable fields as needed.
4. Use Preview to check the result, then Save Project or Export Fillable PDF.

### Add and Place Fields

Click a field type, then click the document to place it. Double-click a field type to keep placing the same type until you press Esc or select another tool.

For Text and Date fields, the click point is treated as the bottom-left corner of the field. If the click is near a detected line, OpenPDFForms tries to size the text box to the line automatically.

During repeated Radio placement, hold `Ctrl+G` on Windows/Linux or `Cmd+G` on Mac to group the radio buttons you click. Release the hotkey to end that group, then hold it again to start another group. Groups are named with short names such as `radio_group_1`.

During Text or Date placement, press `Ctrl+2` through `Ctrl+9` on Windows/Linux or `Cmd+2` through `Cmd+9` on Mac before clicking to split the detected line into that many side-by-side text/date boxes.

### Edit the Base Document

The **Form Editor** section contains objects that become part of the printed page rather than fillable fields:

- **Static Text** adds fixed text such as headings, instructions, or replacement labels.
- **Whiteout** draws a white rectangle over existing page content. This is a visual cover, not secure redaction.
- **Image** inserts a fixed image into the page.

These objects appear in Preview and are included in exported PDFs.

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

The Custom Script section accepts Acrobat JavaScript snippets for format, validation, and calculation events. Button fields can also run selected built-in actions or a custom button-action script. These scripts run only in PDF viewers that execute Acrobat JavaScript, such as Adobe Acrobat/Reader. Viewers without PDF JavaScript support will still show the form fields, but scripted behavior may not run.

Use the script test buttons to check basic syntax and preview simple output before export. Final behavior still depends on the PDF viewer's Acrobat JavaScript support.

Visual conditional logic is converted into Acrobat JavaScript. The generated script is shown in the Inspector and can be copied into the Calculate script box for advanced editing.

### Python Hooks

Copy `hooks.example.py` to `hooks.py` and edit `process_fields()` to rename, filter, or adjust detected fields before they appear in the editor.

## Built-in Access Control

OpenPDFForms includes app-level login and admin user management. On a new install, visit the app and create the first administrator account on the setup page. After signing in, admins can open **Users** from the top toolbar to add users, disable users, reset passwords, grant or remove admin access, and delete users.

Admins can also set session behavior by user:

- **Idle timeout**: no idle timeout, 15 minutes, 30 minutes, 1 hour, or 2 hours.
- **Remember**: keep the login cookie for 1, 7, 30, or 90 days.
- **Logout when browser closes**: use a browser-session cookie instead of a remembered login.

Idle timeout applies server-side as soon as it is changed. Remember duration and browser-close logout affect the user's next login cookie.

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

This project uses PyMuPDF under its free AGPL-3.0-or-later license. If you make OpenPDFForms or a modified version available to other users over a network, AGPL-3.0 requires that those users can access the corresponding source code for the version they are using.

If you cannot satisfy AGPL-3.0 obligations for your use case, obtain a commercial PyMuPDF license from Artifex before deploying the app.

## Third-Party Licenses

This project depends on several third-party libraries, including PyMuPDF under AGPL-3.0-or-later. See `THIRD_PARTY_LICENSES.md` for the full list and what AGPL-3.0 requires if you host a modified version of this app.
