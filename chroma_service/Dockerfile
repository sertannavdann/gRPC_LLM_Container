# Chroma Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY chroma_service/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

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