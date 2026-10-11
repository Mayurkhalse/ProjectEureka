# SAVI Intelligence Platform - Production Dockerfile
# Optimized multi-stage build using Python 3.11 and uv package manager

FROM python:3.11-slim AS builder

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /uvx /bin/

# Copy dependency manifests
COPY pyproject.toml uv.lock ./

# Install dependencies using uv sync into virtual environment
RUN uv sync --frozen --no-install-project --no-dev --extra db

# Copy application source code
COPY src ./src
COPY README.md ./

# Install project package into virtualenv
RUN uv sync --frozen --no-dev --extra db

# ----------------------------------------------------
# Production Runner Image
# ----------------------------------------------------
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY pyproject.toml README.md ./

# Add virtualenv to PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose internal API port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: Production Uvicorn server with 4 worker processes
CMD ["uvicorn", "savi.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
