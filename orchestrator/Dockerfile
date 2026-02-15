FROM python:3.11-slim

# Cache busting argument
ARG CACHE_BUST=1

WORKDIR /app

# System dependencies + grpc_health_probe for health checks
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && GRPC_HEALTH_PROBE_VERSION=v0.4.25 \
    && curl -fsSL https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 -o /usr/local/bin/grpc_health_probe \
    && chmod +x /usr/local/bin/grpc_health_probe

# Python dependencies
COPY orchestrator/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --default-timeout=100 --no-cache-dir -r requirements.txt

# Shared components (clients and proto)
COPY shared/ ./shared/

# Core framework components
COPY core/ ./core/

# Tools components
COPY tools/ ./tools/

# Protobuf files
COPY shared/proto/ ./proto/

# Generate shared protobufs for client imports
RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=./shared/generated \
    --grpc_python_out=./shared/generated \
    proto/llm.proto \
    proto/chroma.proto \
    proto/agent.proto \
    proto/registry.proto \
    proto/worker.proto

# Fix imports in generated gRPC files
RUN find ./shared/generated -name "*_pb2_grpc.py" -type f -exec sed -i 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' {} \;

# Copy orchestrator service code
COPY orchestrator/ ./orchestrator/

# Create data directory for checkpoints
RUN mkdir -p /app/data

ENV PYTHONPATH="${PYTHONPATH}:/app"

EXPOSE 50054
EXPOSE 8888

CMD ["python", "-m", "orchestrator.orchestrator_service"]
