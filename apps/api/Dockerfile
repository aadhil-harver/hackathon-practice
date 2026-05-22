# Multi-stage build for the Interview Prep API.
#
# IMPORTANT: build context is the repo root (not apps/api/), because the
# pyproject.toml + uv.lock live at the repo root and the hatch wheel target
# points at apps/api/src/api. See docker-compose.yml.
#
# Build:   docker build -f apps/api/Dockerfile -t interview-api .
# Run:     docker run --env-file .env -p 8000:8000 interview-api

# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.10-slim AS builder

# Install uv (Astral's Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files first so layer caching kicks in on source-only changes
COPY pyproject.toml uv.lock .python-version README.md ./

# Install deps without the project itself (faster cache hits)
RUN uv sync --no-dev --no-install-project

# Now copy source and install the project. The hatch wheel target is
# "apps/api/src/api", so the package layout has to match here.
COPY apps/api/src ./apps/api/src
RUN uv sync --no-dev

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.10-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/apps/api/src /app/apps/api/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/apps/api/src"

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
