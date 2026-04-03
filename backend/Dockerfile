FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency file first for layer caching
COPY pyproject.toml ./

# Copy backend package
COPY backend/ ./backend/

# Install dependencies
RUN uv sync --no-dev

# Copy entrypoint
COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
