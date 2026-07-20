FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENPDFFORMS_DATA_DIR=/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice libglib2.0-0 libgl1 fonts-dejavu tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY openpdfforms ./openpdfforms

EXPOSE 8000

CMD ["uvicorn", "openpdfforms.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
