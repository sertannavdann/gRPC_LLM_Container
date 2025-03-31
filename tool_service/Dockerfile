FROM python:3.11-slim

WORKDIR /app

COPY tool_service/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY tool_service/tool_service.py .
COPY tool_service/tool_pb2.py .
COPY tool_service/tool_pb2_grpc.py .
COPY tool_service/proto/tool.proto ./proto/

EXPOSE 50053
CMD ["python", "tool_service.py"]
