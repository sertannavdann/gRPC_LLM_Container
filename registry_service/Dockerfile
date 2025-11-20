FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
# We can reuse orchestrator requirements or create a minimal one
COPY orchestrator/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --default-timeout=100 --no-cache-dir -r requirements.txt

# Shared components
COPY shared/ ./shared/

# Protobuf files
COPY shared/proto/ ./proto/

# Generate shared protobufs
RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=./shared/generated \
    --grpc_python_out=./shared/generated \
    proto/registry.proto \
    proto/worker.proto \
    proto/agent.proto \
    proto/llm.proto \
    proto/chroma.proto

# Fix imports
RUN find ./shared/generated -name "*_pb2_grpc.py" -type f -exec sed -i 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' {} \;

# Copy registry service code
COPY registry_service/ ./registry_service/

ENV PYTHONPATH="${PYTHONPATH}:/app"

EXPOSE 50055

CMD ["python", "-m", "registry_service.registry_service"]
