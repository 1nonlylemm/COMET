# syntax=docker/dockerfile:1.7

ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.11


FROM node:${NODE_VERSION}-alpine AS frontend-dev

WORKDIR /app

ENV NODE_ENV=development

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

EXPOSE 3000

CMD ["sh", "-c", "npm install && npm run dev -- --host 0.0.0.0 --port 3000"]


FROM node:${NODE_VERSION}-alpine AS frontend-build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build


FROM nginx:1.27-alpine AS frontend

ENV API_UPSTREAM=http://backend:5000 \
    NGINX_CLIENT_MAX_BODY_SIZE=33554432 \
    DOCUMENT_PREVIEW_TIMEOUT_SECONDS=900

COPY --from=frontend-build /app/dist /usr/share/nginx/html

COPY frontend/nginx/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80


FROM python:${PYTHON_VERSION}-slim AS backend

ENV FLASK_APP=run.py \
    FLASK_CONFIG=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libffi-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    postgresql-client \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY document_fixture_generator/ ./document_fixture_generator/

RUN mkdir -p \
    /app/uploads/branding \
    /app/uploads/guidelines \
    /app/uploads/imports \
    /app/uploads/report_templates \
    /app/uploads/submissions \
    /app/instance/uploads/guidelines \
    /app/instance/object_storage \
    /app/instance/storage_tmp

EXPOSE 5000

CMD ["sh", "-c", "python -m flask db upgrade && gunicorn --workers ${WEB_CONCURRENCY:-2} --timeout ${DOCUMENT_PREVIEW_TIMEOUT_SECONDS:-900} --bind 0.0.0.0:${PORT:-5000} run:app"]


FROM backend AS web

ENV FRONTEND_DIST_DIR=/app/frontend_dist

COPY --from=frontend-build /app/dist /app/frontend_dist

EXPOSE 5000
