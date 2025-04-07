FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY tool_service/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY shared/proto/tool.proto ./proto/
RUN python -m grpc_tools.protoc \
    -I ./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/tool.proto

RUN rm -rf ./proto

COPY tool_service/tool_service.py .

EXPOSE 50053
CMD ["python", "tool_service.py"]