#!/usr/bin/env bash
# Build a self-contained tarball ready to `scp` to a remote server.
#
# Usage:
#   bash scripts/package.sh                 # default: dist/mortgage-intelligence.tar.gz
#   bash scripts/package.sh /tmp/out.tgz    # explicit output path
#
# The tarball expands into a clean `mortgage-intelligence/` directory and
# contains everything needed to run `docker compose -f infra/docker-compose.prod.yml up -d`.
# It excludes .git, node_modules, .venv, .next, secrets (.env, .env.prod),
# and any local on-disk storage cache.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-${ROOT}/dist/mortgage-intelligence.tar.gz}"
mkdir -p "$(dirname "$OUT")"

cd "$ROOT"

# Refresh the requirements.txt snapshot from the current uv lock.
if command -v uv >/dev/null 2>&1; then
  echo "→ Regenerating requirements.txt from uv lock"
  uv export --no-dev --no-hashes --format requirements-txt --output-file requirements.txt >/dev/null
fi

# Stage into a temp dir so the tarball expands into a clean folder name
# regardless of which tar implementation runs (BSD vs GNU).
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
DEST="${STAGE}/mortgage-intelligence"
mkdir -p "$DEST"

echo "→ Staging files"
# Files / directories to include
INCLUDE=(
  backend
  frontend
  infra
  scripts
  docs
  pyproject.toml
  uv.lock
  requirements.txt
)
# Top-level optional docs (don't fail if missing)
for f in README.md improvements.md; do
  [ -e "$f" ] && INCLUDE+=("$f")
done

# rsync gives us cross-platform excludes
RSYNC_EXCLUDES=(
  --exclude='.git'
  --exclude='.venv'
  --exclude='node_modules'
  --exclude='.next'
  --exclude='__pycache__'
  --exclude='*.pyc'
  --exclude='dist'
  --exclude='build'
  --exclude='storage'
  --exclude='infra/.env'
  --exclude='infra/.env.prod'
  --exclude='.DS_Store'
  --exclude='.pytest_cache'
  --exclude='.ruff_cache'
  --exclude='*.tsbuildinfo'
)

rsync -a "${RSYNC_EXCLUDES[@]}" "${INCLUDE[@]}" "$DEST/"

echo "→ Writing $OUT"
( cd "$STAGE" && tar -czf "$OUT" mortgage-intelligence )

SIZE=$(du -h "$OUT" | awk '{print $1}')
echo "✓ Built $OUT ($SIZE)"
echo
echo "Next:"
echo "  scp $OUT user@your-server:/tmp/"
echo "  ssh user@your-server"
echo "  tar -xzf /tmp/$(basename "$OUT") -C ~"
echo "  cd ~/mortgage-intelligence"
echo "  cp infra/.env.prod.example infra/.env.prod && \$EDITOR infra/.env.prod"
echo "  docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod up -d --build"
