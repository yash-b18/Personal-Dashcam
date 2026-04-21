#!/bin/sh
set -e

echo "=== Running alembic migrations ==="
alembic upgrade head

echo "=== Launching uvicorn on port ${PORT:-8000} ==="
exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
