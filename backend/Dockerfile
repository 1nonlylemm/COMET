FROM python:3.11-slim

WORKDIR /app

ENV FLASK_APP=run.py \
    FLASK_CONFIG=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies for WeasyPrint and psycopg2
RUN apt-get update && apt-get install -y \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libffi-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p \
    /app/uploads/branding \
    /app/uploads/guidelines \
    /app/uploads/imports \
    /app/uploads/report_templates \
    /app/uploads/submissions \
    /app/instance/uploads/guidelines \
    /app/instance/object_storage \
    /app/instance/storage_tmp

# Expose port 5000 for Flask
EXPOSE 5000

CMD ["sh", "-c", "python -m flask db upgrade && gunicorn --bind 0.0.0.0:${PORT:-5000} run:app"]
