FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy service code and proto files
COPY tool_service.py .
COPY proto/tool.proto ./proto/
COPY tool_pb2.py .
COPY tool_pb2_grpc.py .

EXPOSE 50053
CMD ["python", "tool_service.py"]
