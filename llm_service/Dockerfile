FROM python:3.11-slim

# Build dependencies
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    cmake build-essential git clang \
    && rm -rf /var/lib/apt/lists/*

ENV CC=clang CXX=clang++

WORKDIR /app

COPY llm_service/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --default-timeout=100 --no-cache-dir -r requirements.txt

COPY shared/proto/llm.proto ./proto/

RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/llm.proto

RUN rm -rf ./proto

COPY llm_service/llm_service.py .
COPY llm_service/config.py .
COPY llm_service/models/ /app/models/

EXPOSE 50051
CMD ["python", "llm_service.py"]