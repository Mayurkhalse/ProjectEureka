FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y libpq-dev gcc curl && rm -rf /var/lib/apt/lists/*

# Install uv for rapid dependency resolution
RUN pip install uv

# Copy requirements and install
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy source code and migration metadata
COPY src/ /app/src/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

# Set environment paths
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Default command for the API (Overridden by Celery in Compose)
CMD ["uvicorn", "eureka.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
