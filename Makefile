# Environment setup
PROTO_DIR := shared/proto
SERVICES := agent_service chroma_service llm_service
# Docker command - use full path if not in conda PATH
DOCKER_CMD := $(shell which docker 2>/dev/null || echo /usr/local/bin/docker)

# Build automation
.PHONY: all proto-gen build up down clean

all: build up

proto-gen:
	@echo "Generating protobuf stubs..."
	@for service in $(SERVICES); do \
		python -m grpc_tools.protoc \
			-I$(PROTO_DIR) \
			--python_out=$$service \
			--grpc_python_out=$$service \
			$(PROTO_DIR)/$$(echo $$service | cut -d'_' -f1).proto; \
		echo "Fixing imports in $$service/*_pb2_grpc.py..."; \
		sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' $$service/*_pb2_grpc.py; \
	done
	@mkdir -p shared/generated
	@echo "Generating shared protobuf stubs..."
	@python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=shared/generated \
		--grpc_python_out=shared/generated \
		$(PROTO_DIR)/cpp_llm.proto \
		$(PROTO_DIR)/llm.proto \
		$(PROTO_DIR)/chroma.proto \
		$(PROTO_DIR)/agent.proto
	@echo "Fixing imports in shared/generated/*_pb2_grpc.py..."
	@sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' shared/generated/*_pb2_grpc.py
	@echo "Protobuf generation complete"

build:
	@echo "Building Docker containers..."
	$(DOCKER_CMD) compose build --parallel
	@echo "Build complete"

up:
	@echo "Starting services..."
	$(DOCKER_CMD) compose up --detach

down:
	@echo "Stopping services..."
	$(DOCKER_CMD) compose down

logs:
	$(DOCKER_CMD) compose logs -f

clean:
	@echo "Cleaning generated files..."
	@find . -name "*_pb2*.py" -delete
	@$(DOCKER_CMD) compose down --volumes --rmi local
	@echo "Clean complete"

health-check:
	@echo "Service Health Status:"
	@for port in 50051 50052 50054; do \
		grpc_health_probe -addr=localhost:$$port -connect-timeout=2s && \
		echo "Port $$port: Healthy" || echo "Port $$port: Unhealthy"; \
	done