FROM python:3.11-slim

WORKDIR /app

COPY agent_service/requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY agent_service/agent_service.py .
COPY agent_service/agent_pb2.py .
COPY agent_service/agent_pb2_grpc.py .
COPY agent_service/proto/agent.proto ./proto/

# Copy shared proto stubs from other services (if not packaged as a library)
COPY llm_service/llm_pb2.py .
COPY llm_service/llm_pb2_grpc.py .
COPY chromadb_service/chroma_pb2.py .
COPY chromadb_service/chroma_pb2_grpc.py .
COPY tool_service/tool_pb2.py .
COPY tool_service/tool_pb2_grpc.py .

EXPOSE 50054
CMD ["python", "agent_service.py"]
