FROM python:3.11-slim

WORKDIR /app

# Install dependencies (including git for pip packages if needed)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy service code and proto files
COPY chroma_service.py .
COPY proto/ ./proto/
COPY chroma_pb2.py .
COPY chroma_pb2_grpc.py .

EXPOSE 50052
CMD ["python", "chroma_service.py"]
