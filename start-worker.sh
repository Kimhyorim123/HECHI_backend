#!/bin/sh
set -e
# Run migrations to ensure DB schema present
if [ -f ./alembic.ini ]; then
	alembic upgrade head || echo "[WARN] alembic upgrade failed, continuing"
else
	echo "[WARN] alembic.ini not found; skipping migrations"
fi
exec python worker/worker.py
