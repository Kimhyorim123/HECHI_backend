# Bookstopper Backend

Backend service for the Bookstopper application.

## Stack
- FastAPI
- MySQL
- Docker Compose
- Nginx
- Background Worker
- OpenAI / Firebase / Aladin API integration

## What To Commit
Commit these files to GitHub so the project can be restored later:
- application code under `app/`
- background worker code under `worker/`
- database migrations under `migrations/versions/`
- `docker-compose.yml`
- `Dockerfile.api`, `Dockerfile.worker`, `Dockerfile.nginx`
- `nginx/nginx.conf`
- `requirements.txt`
- `README.md`
- `.env.example`
- committed API docs under `docs/openapi-v1.1.json`

Do not commit:
- `.env`
- Firebase service account json
- real API keys / passwords
- local uploaded files under `uploads/`
- database dumps unless you intentionally store backups elsewhere

## First-Time Setup
```bash
git clone <YOUR_GITHUB_REPO_URL>
cd bookstopper-backend
cp .env.example .env
```

Fill in the real values inside `.env` before starting containers. In particular, set the database passwords, API keys, and the Firebase JSON host path if you use notifications.

## Run With Docker Compose
```bash
docker compose up -d --build
```

## Stop Containers
```bash
docker compose down
```

## Apply Migrations
If your deployment flow requires manual migration execution, run:

```bash
docker compose exec api alembic upgrade head
```

If container names are already fixed in the running server, you can also use:

```bash
docker exec -it bookstopper-api alembic upgrade head
```

## Restore After Pull
When you pull the repository on the same server or a new server, the minimum restore flow is:

```bash
git pull origin main
cp .env.example .env   # only if .env does not exist yet
# fill real env values

docker compose up -d --build
docker compose exec api alembic upgrade head
```

If you keep the Firebase service-account file outside the repository, point `FCM_SERVICE_ACCOUNT_JSON_HOST_PATH` in `.env` to that host file and keep `FCM_SERVICE_ACCOUNT_JSON_PATH` at the in-container path used by the app.

## Important: Code Backup Is Not Full Service Backup
GitHub alone restores the codebase, but not the live service state.
To restore the project exactly as it was, you also need:
- database backup
- uploaded file backup
- real `.env` values
- Firebase credential file

## Database Backup
Create a MySQL dump:

```bash
docker exec bookstopper-db mysqldump -u bookstopper -p'YOUR_DB_PASSWORD' bookstopper > backup_bookstopper.sql
```

Restore it later:

```bash
docker exec -i bookstopper-db mysql -u bookstopper -p'YOUR_DB_PASSWORD' bookstopper < backup_bookstopper.sql
```

## Uploaded Files Backup
This project currently supports local file uploads. If you are not using S3, uploaded files must be backed up separately.

Create backup:

```bash
tar -czf uploads_backup.tar.gz uploads/
```

Restore backup:

```bash
tar -xzf uploads_backup.tar.gz
```

## Recommended Backup Set
For a real recovery point, keep all of the following together:
- GitHub repository
- `.env` file stored securely outside GitHub
- Firebase admin sdk json stored securely outside GitHub
- `backup_bookstopper.sql`
- `uploads_backup.tar.gz`

## Current Upload Strategy
- Group images and profile images can use `/uploads/presign`
- If S3 is not configured, uploads fall back to local storage
- Local uploaded files are served from `/static/uploads/`

## API Docs
Committed OpenAPI spec:
- `docs/openapi-v1.1.json`
