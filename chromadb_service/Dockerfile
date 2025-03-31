FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY chromadb_service/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY chromadb_service/chroma_service.py .
COPY chromadb_service/chroma_pb2.py .
COPY chromadb_service/chroma_pb2_grpc.py .
COPY chromadb_service/proto/chroma.proto ./proto/

# Create directory for persistent data
RUN mkdir -p /app/data

EXPOSE 50052
CMD ["python", "chroma_service.py"]
