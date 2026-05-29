#!/bin/sh
set -e

PORT="${PORT:-8000}"

echo "Running database migrations..."
uv run alembic -c backend/db/alembic.ini upgrade head

echo "Starting backend server on port ${PORT}..."
exec uv run uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}"
