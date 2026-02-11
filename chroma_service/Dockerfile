# Chroma Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies + grpc_health_probe for health checks
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && GRPC_HEALTH_PROBE_VERSION=v0.4.25 \
    && curl -fsSL https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 -o /usr/local/bin/grpc_health_probe \
    && chmod +x /usr/local/bin/grpc_health_probe

# Python dependencies
COPY chroma_service/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --default-timeout=100 --no-cache-dir -r requirements.txt

# Shared components
COPY shared/ ./shared/
COPY shared/proto/ ./proto/

# Generate protobuf stubs
RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/chroma.proto

# Application code
COPY chroma_service/chroma_service.py .

ENV PYTHONPATH="${PYTHONPATH}:/app"

VOLUME /app/data
EXPOSE 50052
CMD ["python", "chroma_service.py"]