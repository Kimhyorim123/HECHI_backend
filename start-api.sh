#!/bin/sh
set -e
# Run migrations before starting API
if [ -f ./alembic.ini ]; then
	alembic upgrade head || echo "[WARN] alembic upgrade failed, continuing"
else
	echo "[WARN] alembic.ini not found; skipping migrations"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
