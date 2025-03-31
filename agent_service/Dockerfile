FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY agent_service/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy agent service code and its proto files
COPY agent_service/agent_service.py .
COPY agent_service/proto/ ./proto/

# Copy proto stubs from sibling services (now accessible because build context is the project root)
COPY llm_service/llm_pb2.py .
COPY llm_service/llm_pb2_grpc.py .
COPY chromadb_service/chroma_pb2.py .
COPY chromadb_service/chroma_pb2_grpc.py .
COPY tool_service/tool_pb2.py .
COPY tool_service/tool_pb2_grpc.py .

EXPOSE 50054
CMD ["python", "agent_service.py"]
