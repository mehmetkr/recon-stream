FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install system dependencies for psycopg (PostgreSQL adapter)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Copy pyproject.toml and create minimal src/ stub so setuptools can discover packages
COPY pyproject.toml .
RUN mkdir -p src && pip install --no-cache-dir ".[dev]"

# Copy entrypoint and fix CRLF (Windows compatibility)
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh \
    && chmod +x /entrypoint.sh

# Copy application code
COPY src/ src/

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "src/manage.py", "runserver", "0.0.0.0:8000"]
