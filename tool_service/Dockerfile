# Tool Service Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    unzip \
    libgconf-2-4 \
    libnss3 \
    libxi6 \
    libappindicator1 \
    fonts-liberation \
    xvfb \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY tool_service/requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY tool_service/tool_service.py .
COPY tool_service/tool_pb2.py .
COPY tool_service/tool_pb2_grpc.py .
COPY tool_service/proto/tool.proto ./proto/

EXPOSE 50053
CMD ["python", "tool_service.py"]
