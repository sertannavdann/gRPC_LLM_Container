FROM python:3.11-slim

# Install necessary build tools including clang
RUN apt-get update && \
    apt-get install -y cmake build-essential git clang && \
    rm -rf /var/lib/apt/lists/*

# Set Clang as the default compiler
ENV CC=clang
ENV CXX=clang++

WORKDIR /app

# Install Python dependencies
COPY llm_service/requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy service code and generated proto files
COPY llm_service/llm_service.py .
COPY llm_service/proto/llm.proto ./proto/
COPY llm_service/llm_pb2.py .
COPY llm_service/llm_pb2_grpc.py .

# Copy your models folder (ensure the model file is there)
COPY llm_service/models/ /app/models/

EXPOSE 50051
CMD ["python", "llm_service.py"]