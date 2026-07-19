# Third-Party Licenses

OpenPDFForms is licensed under AGPL-3.0-or-later (see `LICENSE`). It depends
on the following third-party libraries, each under its own license:

| Library | License | Project |
|---|---|---|
| PyMuPDF (`fitz`) | AGPL-3.0-or-later (or Artifex commercial license) | https://github.com/pymupdf/PyMuPDF |
| pyHanko | MIT | https://github.com/MatthiasValvekens/pyHanko |
| cryptography | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography |
| FastAPI | MIT | https://github.com/fastapi/fastapi |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| Pydantic | MIT | https://github.com/pydantic/pydantic |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart |
| Pillow | MIT-CMU | https://github.com/python-pillow/Pillow |
| OpenCV (`opencv-python-headless`) | Apache-2.0 | https://github.com/opencv/opencv-python |
| NumPy | BSD-3-Clause and others | https://numpy.org |

## PyMuPDF and AGPL-3.0

This project uses PyMuPDF under the free AGPL-3.0-or-later license (rather
than Artifex's paid commercial license). AGPL-3.0 requires that anyone who
interacts with this software over a network be offered the corresponding
source code. Because OpenPDFForms is run as a hosted web app, its own
source is published at:

https://github.com/jlrosssc/OpenPDFForms

If you deploy a modified version of OpenPDFForms and make it available to
other users over a network, AGPL-3.0 (via PyMuPDF) requires you to offer
those users the source of your modified version as well.

If you cannot satisfy AGPL-3.0 obligations for a deployment, use a
commercial PyMuPDF license from Artifex instead of the free AGPL-3.0
license.

## Python Dependency Notes

The pinned packages in `requirements.txt` may install additional
transitive dependencies. Those dependencies remain under their own
licenses. Common examples include Starlette, AnyIO, Click, h11,
httptools, watchfiles, websockets, cffi, pycparser, asn1crypto,
tzlocal, PyYAML, qrcode, and related packages pulled in by FastAPI,
Uvicorn, pyHanko, cryptography, and their extras.

When distributing a built Docker image or other binary artifact, include
the license notices for both the direct and transitive packages present
in that artifact.

## Separate Container Images

The optional deployment files can run separate services alongside
OpenPDFForms:

| Service | Image | Notice |
|---|---|---|
| nginx reverse proxy | `nginx:1.27-alpine` | nginx and Alpine Linux remain under their own licenses. |
| Stirling PDF | `docker.stirlingpdf.com/stirlingtools/stirling-pdf:latest-fat` | Stirling PDF is a separate open-core PDF application under its own licensing. |

These services are not bundled as source code in this repository. Review
the license terms for the exact container image versions you deploy.


## Adobe Compatibility References

OpenPDFForms implements standards-based PDF AcroForm fields and Acrobat JavaScript-compatible snippets for interoperability. Adobe Acrobat, Adobe Reader, Adobe Sign, Acrobat JavaScript, and related names are trademarks or product names of Adobe or its affiliates. They are referenced only to describe compatibility goals and user expectations; no Adobe source code, SDK code, fonts, icons, or proprietary assets are bundled in this repository.

Useful public references for implementers include Adobe's Acrobat JavaScript documentation and public Acrobat form/signature help pages. Those documents are external references only and are not incorporated into this project as source material.
