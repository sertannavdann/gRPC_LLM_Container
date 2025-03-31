proto-gen:
	python -m grpc_tools.protoc -I./llm_service/proto --python_out=llm_service --grpc_python_out=llm_service ./llm_service/proto/llm.proto
	python -m grpc_tools.protoc -I./agent_service/proto --python_out=agent_service --grpc_python_out=agent_service ./agent_service/proto/agent.proto
	python -m grpc_tools.protoc -I./chromadb_service/proto --python_out=chromadb_service --grpc_python_out=chromadb_service ./chromadb_service/proto/chroma.proto
	python -m grpc_tools.protoc -I./tool_service/proto --python_out=tool_service --grpc_python_out=tool_service ./tool_service/proto/tool.proto

build:
	docker-compose build

up:
	docker-compose up

down:
	docker-compose down
