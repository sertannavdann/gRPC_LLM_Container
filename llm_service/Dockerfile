FROM python:3.11-slim

# Build dependencies + grpc_health_probe for health checks
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    cmake build-essential git clang curl \
    && rm -rf /var/lib/apt/lists/* \
    && GRPC_HEALTH_PROBE_VERSION=v0.4.25 \
    && curl -fsSL https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 -o /usr/local/bin/grpc_health_probe \
    && chmod +x /usr/local/bin/grpc_health_probe

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

EXPOSE 50051
CMD ["python", "llm_service.py"]