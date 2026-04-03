#!/bin/sh
set -e

echo "Running database migrations..."
uv run alembic -c backend/db/alembic.ini upgrade head

echo "Starting backend server..."
exec uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
