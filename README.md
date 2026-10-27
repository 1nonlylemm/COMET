# DILG Operations Workspace

DILG Operations Workspace is an internal DILG workflow system for PDMU staff and field-side officers. It is built to support documentary triage, implementation monitoring, notice/escalation handling, regional Google Drive handoff, and completion/reportorial tracking.

For current assistant coverage, role restrictions, supported imports/downloads and remaining gaps, see the [Smart Assistant capability checklist](references/SMART_ASSISTANT_CAPABILITY_CHECKLIST.md). In the expanded assistant, **Available Actions** lists the actions for your account. Ask **“what can you do?”** for a summary from the live registry.

For domain knowledge, workflow sources and the distinction between policy and software implementation, see the [Knowledge Brain documentation](backend/app/brain/README.md).

## Tech Stack

- Backend: Flask, SQLAlchemy, Alembic, JWT, Celery
- Frontend: React, Vite, React Router
- Database: PostgreSQL 15
- Queue/worker: Redis
- Documents: WeasyPrint, docxtpl
- Optional integrations: Brevo SMTP, Google Drive, Gemini

## Repository Structure

```text
project-root/
├─ backend/         Flask API, models, services, migrations, tests
├─ frontend/        React app
├─ references/      Retained assistant capability and checker references
├─ tooling/         Helper scripts and MCP templates
├─ docker-compose.yml
├─ .env.example
└─ README.md
```

## Prerequisites

### Recommended path: Docker

Install these first:
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Git

### Optional local path

If you want to run services outside Docker, install:
- Python 3.11
- Node.js 22
- PostgreSQL 15
- Redis 7

## Quick Start With Docker

### 1. Clone the repo

```powershell
git clone <your-repo-url>
cd <repo-folder>
```

### 2. Create your root `.env`

If you do not already have one:

```powershell
Copy-Item .env.example .env
```

Then edit [`.env`](.env).

Current required values for the default Docker setup:

```env
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your-brevo-smtp-login
SMTP_PASSWORD=your-brevo-smtp-key
MAIL_FROM=your-verified-sender@example.com
APP_LOGIN_URL=http://localhost:3000/login
APP_NAME=DILG Operations Workspace
APP_TAGLINE=DILG Laguna PDMU Operations System
```

Notes:
- For local development, SMTP is optional. If SMTP is not configured correctly, account provisioning falls back to manual credential handoff.
- The current Docker setup reads these values for `backend`, `celery_worker`, and `celery_beat`.

### 3. Start the stack

```powershell
docker compose up --build -d
```

What starts:
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`
- Backend API on `http://localhost:5000`
- Frontend on `http://localhost:3000`
- pgAdmin on `http://localhost:5050`

### 4. Wait for migrations to finish

The backend container automatically runs migrations on startup.

You can inspect the container logs to verify they finished successfully:

```powershell
docker compose logs backend --tail=100
```

### 5. Initialize access safely

Migrations initialize the schema. This repository does not provide a dedicated
production administrator bootstrap command. Arrange initial administrator access
with the system owner through an approved secure process before handover.

`backend/seed.py` and `backend/seed_demo.py` are retained for maintained tests and
disposable development environments. They create synthetic users with public test
passwords and may reset data. Never use them to initialize or refresh production.
Do not reuse test accounts or passwords for client access.

The development frontend is available at `http://localhost:3000` and the API at
`http://localhost:5000`. Configure pgAdmin access in the development Compose file;
its defaults are for disposable local use only.

### Durable file storage

For production-like local runs, configure Cloudflare R2 in `.env`:

```env
OBJECT_STORAGE_PROVIDER=r2
OBJECT_STORAGE_ENV=local
OBJECT_STORAGE_BUCKET_PREFIX=comet
R2_BUCKET_NAME=dilg-pdmu-comet-files
R2_ACCOUNT_ID=your-cloudflare-account-id
R2_ENDPOINT_URL=https://your-account-id.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your-r2-access-key
R2_SECRET_ACCESS_KEY=your-r2-secret-key
R2_REGION=auto
```

`seed_demo.py` stores new DMS evidence and guideline files through the configured object-storage provider while keeping local paths as a compatibility cache.

## Common Development Commands

### Docker

Start services:

```powershell
docker compose up -d
```

Rebuild services:

```powershell
docker compose up --build -d
```

Stop services:

```powershell
docker compose down
```

Persistent volumes contain database data. Retain them when stopping the stack.

Open a shell inside the backend container:

```powershell
docker compose exec backend sh
```

### Backend tests

```powershell
docker compose exec backend python -m pytest -q
```

### Frontend build check

```powershell
cd frontend
npm run build
```

## Local Setup Without Docker

Use this only if you specifically want to run the services directly on your machine.

### 1. Start PostgreSQL and Redis

Create a database named `workspace_db`.

Example connection string:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/workspace_db
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 2. Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m flask db upgrade
python -m flask run --host=0.0.0.0 --port=5000
```

Optional worker terminals:

```powershell
cd backend
.venv\Scripts\Activate.ps1
celery -A app.tasks.celery_app worker --loglevel=info
```

```powershell
cd backend
.venv\Scripts\Activate.ps1
celery -A app.tasks.celery_app beat --loglevel=info
```

### 3. Frontend setup

```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

## Optional Integrations

### Brevo SMTP

Used for internal account provisioning email when enabled.

Root `.env` keys:

```env
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your-brevo-smtp-login
SMTP_PASSWORD=your-brevo-smtp-key
MAIL_FROM=your-verified-sender@example.com
```

### Google Drive handoff

The backend supports Google Drive handoff, but it is optional for local setup.

Relevant backend config keys:
- `GOOGLE_DRIVE_ENABLED`
- `GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE`
- `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_DRIVE_ROOT_FOLDER_ID`
- `GOOGLE_DRIVE_SHARED_DRIVE_ID`

The Docker Compose files pass these settings to the backend. Supply the client configuration through the environment.

### AWS document compliance enhancement

The documentary compliance checker is local-first. AWS is optional and disabled by default.

Relevant backend config keys:
- `DOCUMENT_AWS_ENABLED`
- `DOCUMENT_AWS_REGION`
- `DOCUMENT_AWS_PROFILE_NAME`
- `DOCUMENT_AWS_TEXTRACT_ENABLED`
- `DOCUMENT_AWS_REKOGNITION_ENABLED`
- `DOCUMENT_AWS_TEXTRACT_FEATURE_TYPES`
- `DOCUMENT_AWS_REKOGNITION_MAX_LABELS`
- `DOCUMENT_AWS_REKOGNITION_MIN_CONFIDENCE`
- `DOCUMENT_AWS_LOCATION_ENABLED`
- `DOCUMENT_AWS_LOCATION_PLACE_INDEX`
- `DOCUMENT_AWS_LOCATION_LANGUAGE`
- `DOCUMENT_AWS_ENABLED_FOR_TESTING`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN`

The least-privilege IAM policy for the first pass needs `textract:AnalyzeDocument`, `textract:AnalyzeExpense`, and `rekognition:DetectLabels`. If photo GPS reverse geocoding is enabled, also grant `geo:SearchPlaceIndexForPosition` on the configured Amazon Location Service place index. Provider output is advisory and is recorded in checker metadata; it does not auto-approve evidence.

### Gemini AI drafting

Optional backend config keys:
- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`
- `GEMINI_MODEL`

If these are not set, AI-assisted drafting features will not be active.

## Upload Rules

Backend defaults without environment overrides:
- maximum submission size: `25 MiB` (`MAX_SUBMISSION_FILE_BYTES`); request limit: `32 MiB` (`MAX_CONTENT_LENGTH`)
- allowed extensions: `pdf, doc, docx, xls, xlsx, ppt, pptx, jpg, jpeg, png, csv`

Relevant config keys:
- `MAX_SUBMISSION_FILE_BYTES`
- `SUBMISSION_ALLOWED_EXTENSIONS`
- `SUBMISSION_ALLOWED_MIME_TYPES`

## Production deployment

Use `docker-compose.prod.yml` with a private `.env` based on
`.env.production.example`. Replace every placeholder and set the client URLs,
storage settings and integration credentials. Keep the encryption key stable
across deployments. Development Compose credentials are public fixtures.

Validate configuration and build images before deployment:

```powershell
docker compose --env-file .env -f docker-compose.prod.yml config --quiet
docker compose --env-file .env -f docker-compose.prod.yml build
```

During the approved deployment window, back up the database and stored files,
then apply migrations before starting the updated application and workers:

```powershell
docker compose --env-file .env -f docker-compose.prod.yml run --rm --no-deps backend python -m flask db upgrade
docker compose --env-file .env -f docker-compose.prod.yml up -d
```

Production services require PostgreSQL, Redis, Celery worker and Celery Beat.
Preserve persistent volumes and upload/object-store directories. Verify `/api/health`,
authenticated role access, document processing and configured integrations after deployment.
The existing GitHub workflow deploys pushes to `main`; configure its secrets and
intended destination before enabling it in a client repository.

## Troubleshooting

### Backend login returns an internal server error after pulling changes

Run migrations again:

```powershell
docker compose exec backend python -m flask db upgrade
```

If needed, recreate backend services:

```powershell
docker compose up -d --force-recreate backend celery_worker celery_beat
```

### Frontend redirects unexpectedly or looks stale

Rebuild/restart the frontend and do a hard refresh in the browser:

```powershell
docker compose up -d --build frontend
```

### Seed script wiped my data

That is expected. `backend/seed.py` is destructive and intended for local development only.

### SMTP is not sending emails

Check:
- your Brevo credentials
- verified sender address in `MAIL_FROM`
- backend logs:

```powershell
docker compose logs backend --tail=100
```

## Project Operating Notes

- No public self-registration
- Internal users only
- Field officers are internal users in the workflow
- The application is not a SubayBAYAN replacement
- Consult the runtime knowledge sources in `backend/app/brain/` for workflow context
- Use neutral branch names that describe the product/work scope only.
