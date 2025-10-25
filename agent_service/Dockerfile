FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y protobuf-compiler && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY agent_service/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --default-timeout=100 --no-cache-dir -r requirements.txt

# Shared components (including pre-generated protobuf files)
COPY shared/ ./shared/

# Generate local protobuf stubs for agent service
COPY shared/proto/ ./proto/
RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/agent.proto

# Application code
COPY agent_service/agent_service.py .

ENV PYTHONPATH="${PYTHONPATH}:/app"

EXPOSE 50054
CMD ["python", "agent_service.py"]