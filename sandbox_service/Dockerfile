FROM python:3.11-slim

WORKDIR /app

# Security: Create non-root user for sandbox execution
RUN groupadd -r sandbox && useradd -r -g sandbox sandbox

# Install system dependencies + grpc_health_probe for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && GRPC_HEALTH_PROBE_VERSION=v0.4.25 \
    && curl -fsSL https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 -o /usr/local/bin/grpc_health_probe \
    && chmod +x /usr/local/bin/grpc_health_probe

# Copy requirements and install
COPY sandbox_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared protobuf files
COPY shared/proto/ /app/shared/proto/
COPY shared/generated/ /app/shared/generated/

# Copy service code
COPY sandbox_service/ /app/sandbox_service/

# Set working directory
WORKDIR /app/sandbox_service

# Ensure sandbox user owns application directory
RUN chown -R sandbox:sandbox /app

# Security: Set resource limits via environment
ENV SANDBOX_TIMEOUT=30
ENV SANDBOX_MEMORY_MB=256

# Run container as non-root sandbox user
USER sandbox

EXPOSE 50057

CMD ["python", "sandbox_service.py"]
