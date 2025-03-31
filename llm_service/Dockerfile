FROM python:3.11-slim

WORKDIR /app

# Install build dependencies (if needed for llama-cpp-python)
RUN apt-get update && apt-get install -y cmake build-essential && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application code and proto files
COPY llm_service.py .
COPY proto/ ./proto/

# Copy the llama-cli binary and model files
COPY llama/ ./llama/
COPY models/ ./models/

EXPOSE 50051
CMD ["python", "llm_service.py"]
