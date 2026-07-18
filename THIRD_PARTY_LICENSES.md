# Third-Party Licenses

OpenPDFForms is licensed under GPL-2.0-or-later (see `LICENSE`). It depends
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
