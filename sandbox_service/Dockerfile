FROM python:3.11-slim

WORKDIR /app

# Security: Create non-root user for sandbox execution
RUN groupadd -r sandbox && useradd -r -g sandbox sandbox

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY sandbox_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared protobuf files
COPY shared/proto/ /app/shared/proto/
COPY shared/generated/ /app/shared/generated/

# Copy service code
COPY sandbox_service/ /app/sandbox_service/

# Set working directory
WORKDIR /app/sandbox_service

# Security: Set resource limits via environment
ENV SANDBOX_TIMEOUT=30
ENV SANDBOX_MEMORY_MB=256

# Run as non-root user for code execution
# Note: The service itself runs as root but switches to sandbox user for code execution

EXPOSE 50057

CMD ["python", "sandbox_service.py"]
