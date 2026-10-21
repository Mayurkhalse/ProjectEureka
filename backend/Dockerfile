FROM python:3.12-slim

WORKDIR /app

# Install minimal system dependencies required for runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy runtime requirements only and install into system Python
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy backend source code, migrations and configuration
COPY src/ /app/src/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

# Set environment variables
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Create non-root user and assign permissions
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose default port
EXPOSE 8000

# Healthcheck on /api/v1/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health || exit 1

# Start Uvicorn bound to 0.0.0.0 on dynamically assigned $PORT
CMD ["sh", "-c", "uvicorn eureka.api.main:app --host 0.0.0.0 --port ${PORT}"]
