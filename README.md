# OpenPDFForms

OpenPDFForms is a local web app for turning flat or scanned PDFs into fillable PDF forms.

The first version focuses on a practical review workflow:

- Upload a PDF.
- Render each page in the browser.
- Auto-detect likely text fields, checkboxes, and radio buttons.
- Edit, move, resize, add, or delete fields.
- Save and reopen editable OpenPDFForms projects.
- Create a signature by drawing with a mouse/touch input or typing a script-style facsimile.
- Export a fillable AcroForm PDF.
- Customize detection and field naming with Python hooks.

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

This is intentionally local-first. Uploaded PDFs are stored in `data/uploads`, rendered page images in `data/renders`, and exported PDFs in `data/exports`.

The detector is heuristic-based in this first version. It uses PDF text geometry and page rendering analysis to find likely fields, then expects a human to review the overlay before export.

## Workflow

OpenPDFForms separates the editable project from the distributable PDF:

- **Save Project** stores the original PDF plus edited field layout under `data/projects`.
- **Open Project** reopens the editable overlay later.
- **Export Fillable PDF** creates the PDF you can distribute to other people.

Signature fields support two facsimile modes:

- **Draw** with mouse, trackpad, stylus, or touch.
- **Type** a name and render it using a cursive/script font stack.

When a signature is applied to a signature field, export embeds it as visible PDF content.

## Third-Party Licenses

This project depends on several third-party libraries, including PyMuPDF
under AGPL-3.0-or-later. See `THIRD_PARTY_LICENSES.md` for the full list
and what AGPL-3.0 requires if you host a modified version of this app.
