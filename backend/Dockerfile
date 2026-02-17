FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app /app/app

# Create storage directory with proper permissions
RUN mkdir -p /app/storage/raw && \
    chmod -R 755 /app/storage

# Add non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health/liveness || exit 1

# Production uvicorn configuration
# Use single worker to prevent multi-process lifespan race conditions.
# For horizontal scaling, use container replicas instead.
CMD ["sh", "-c", "uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers ${WORKERS:-1} \
    --log-level $(echo ${LOG_LEVEL:-INFO} | tr '[:upper:]' '[:lower:]') \
    --timeout-keep-alive 5 \
    --timeout-graceful-shutdown 30 \
    --access-log"]
