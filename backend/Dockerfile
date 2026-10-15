FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including libpq and build essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and alembic files
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini .

# Set PYTHONPATH so src is in module path
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "eureka.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
