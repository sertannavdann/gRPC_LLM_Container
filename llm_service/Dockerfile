FROM python:3.11-slim

WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y cmake build-essential && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY llm_service/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy entire llm_service folder (ensure llm_pb2.py etc. are inside llm_service/)
COPY llm_service/ ./

# Copy your local llama-cli binary from the repository's "llama" directory
COPY llama /app/llama

EXPOSE 50051
CMD ["python", "llm_service.py"]
