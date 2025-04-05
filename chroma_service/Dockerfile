FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    python3-grpcio-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY shared/proto/chroma.proto ./proto/

RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/chroma.proto

COPY chromadb_service/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN rm -rf ./proto

COPY chromadb_service/chroma_service.py .

# Persistent storage
VOLUME /app/data

EXPOSE 50052
CMD ["python", "chroma_service.py"]