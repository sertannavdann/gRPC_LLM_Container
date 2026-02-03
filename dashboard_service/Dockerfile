FROM python:3.11-slim

# Cache busting argument
ARG CACHE_BUST=1

WORKDIR /app

# System dependencies (minimal for this service)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY dashboard_service/requirements.txt ./dashboard_service/
RUN pip install --upgrade pip && \
    pip install --default-timeout=100 --no-cache-dir -r dashboard_service/requirements.txt

# Copy shared components (adapters, schemas)
COPY shared/ ./shared/

# Copy dashboard service code
COPY dashboard_service/ ./dashboard_service/

# Set Python path to include app root
ENV PYTHONPATH="${PYTHONPATH}:/app"

# Configuration via environment variables
ENV HOST="0.0.0.0"
ENV PORT="8080"
ENV CACHE_TTL_SECONDS="300"
ENV CORS_ORIGINS="*"
ENV DEBUG="false"

# Expose HTTP port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the service
CMD ["python", "-m", "uvicorn", "dashboard_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
