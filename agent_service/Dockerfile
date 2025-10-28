FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y protobuf-compiler && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY agent_service/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --default-timeout=100 --no-cache-dir -r requirements.txt

# Copy router model and llama-cli binary from llm_service
COPY llm_service/models/qwen2.5-3b-instruct-q5_k_m.gguf ./models/
COPY llm_service/llama/llama-cli ./llama/
RUN chmod +x ./llama/llama-cli

# Shared components (including pre-generated protobuf files)
COPY shared/ ./shared/

# Core framework components
COPY core/ ./core/

# Tools components
COPY tools/ ./tools/

# Generate protobuf stubs
COPY shared/proto/ ./proto/

# Generate agent service protobuf
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
    proto/cpp_llm.proto \
    proto/llm.proto \
    proto/chroma.proto \
    proto/agent.proto

# Fix imports in generated gRPC files
RUN find ./shared/generated -name "*_pb2_grpc.py" -type f -exec sed -i 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' {} \;

# Application code
COPY agent_service/agent_service.py .
COPY agent_service/adapter.py .
COPY agent_service/llm_wrapper.py .

ENV PYTHONPATH="${PYTHONPATH}:/app"

EXPOSE 50054
CMD ["python", "agent_service.py"]