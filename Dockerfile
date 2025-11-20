# Production Dockerfile for Zenzefi Backend
FROM python:3.13-slim

# Build arguments for cache invalidation
ARG BUILDTIME
ARG GIT_SHA
ENV BUILD_ID=${BUILDTIME} \
    GIT_COMMIT=${GIT_SHA}

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.3

# Copy project files
COPY pyproject.toml poetry.lock ./

# Configure Poetry and install dependencies
# - no virtualenv (running in container)
# - no dev dependencies (production)
# - no root (app package installed separately)
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-root --no-interaction --no-ansi

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create logs directory
RUN mkdir -p /app/logs

# Create non-root user for security
RUN useradd -m -u 1000 zenzefi && chown -R zenzefi:zenzefi /app
USER zenzefi

# Expose port (not strictly necessary as container networking handles it)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run migrations and start application
CMD poetry run alembic upgrade head && \
    poetry run uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info \
    --access-log \
    --proxy-headers \
    --forwarded-allow-ips '*'