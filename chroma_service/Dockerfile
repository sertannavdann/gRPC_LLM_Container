# Updated Agent Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y protobuf-compiler && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY agent_service/requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy shared components
COPY shared/ ./shared/
COPY shared/proto/ ./proto/

# Generate protobuf stubs
RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/*.proto

# Copy application code
COPY agent_service/agent_service.py .

ENV PYTHONPATH="${PYTHONPATH}:/app"

EXPOSE 50054
CMD ["python", "agent_service.py"]