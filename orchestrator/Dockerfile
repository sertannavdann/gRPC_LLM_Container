FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

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

# Generate protobuf stubs for agent service (orchestrator uses agent.proto)
RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/agent.proto

# Generate shared protobufs for client imports
RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=./shared/generated \
    --grpc_python_out=./shared/generated \
    proto/llm.proto \
    proto/chroma.proto \
    proto/agent.proto

# Fix imports in generated gRPC files
RUN find ./shared/generated -name "*_pb2_grpc.py" -type f -exec sed -i 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' {} \;

# Copy orchestrator service code
COPY orchestrator/ ./orchestrator/

# Create data directory for checkpoints
RUN mkdir -p /app/data

ENV PYTHONPATH="${PYTHONPATH}:/app"

EXPOSE 50054

CMD ["python", "-m", "orchestrator.orchestrator_service"]
