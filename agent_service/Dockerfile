# agent_service/Dockerfile (pattern repeats for other services)
FROM python:3.11-slim

# Add protobuf compiler
RUN apt-get update && apt-get install -y protobuf-compiler python3-grpcio-tools && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy all proto files to shared directory
COPY proto/agent.proto proto/llm.proto proto/chroma.proto proto/tool.proto ./proto/

# Generate stubs during build
RUN python -m grpc_tools.protoc -I ./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/*.proto

# Rest remains same
COPY agent_service/requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY agent_service/agent_service.py .
EXPOSE 50054
CMD ["python", "agent_service.py"]