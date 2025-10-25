# Environment setup
PROTO_DIR := shared/proto
SERVICES := agent_service chroma_service llm_service ui_service
# Docker command - use full path if not in conda PATH
DOCKER_CMD := $(shell which docker 2>/dev/null || echo /usr/local/bin/docker)

# Build automation
.PHONY: all proto-gen build up down clean

all: build up

# Main proto-gen target
proto-gen: proto-gen-agent proto-gen-chroma proto-gen-llm proto-gen-shared
	@echo "All protobufs generated."

# Individual proto-gen targets
proto-gen-agent:
	@echo "Generating agent protobuf stubs..."
	@python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=agent_service \
		--grpc_python_out=agent_service \
		$(PROTO_DIR)/agent.proto
	@sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' agent_service/*_pb2_grpc.py

proto-gen-chroma:
	@echo "Generating chroma protobuf stubs..."
	@python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=chroma_service \
		--grpc_python_out=chroma_service \
		$(PROTO_DIR)/chroma.proto
	@sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' chroma_service/*_pb2_grpc.py

proto-gen-llm:
	@echo "Generating llm protobuf stubs..."
	@python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=llm_service \
		--grpc_python_out=llm_service \
		$(PROTO_DIR)/llm.proto
	@sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' llm_service/*_pb2_grpc.py

proto-gen-shared:
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

# Main build target
build:
	@echo "Building all Docker containers..."
	$(DOCKER_CMD) compose build --parallel
	@echo "Build complete"

# Individual build targets
build-agent:
	@echo "Building agent_service container..."
	$(DOCKER_CMD) compose build agent_service
	@echo "Build complete"

build-chroma:
	@echo "Building chroma_service container..."
	$(DOCKER_CMD) compose build chroma_service
	@echo "Build complete"

build-llm:
	@echo "Building llm_service container..."
	$(DOCKER_CMD) compose build llm_service
	@echo "Build complete"

build-ui:
	@echo "Building ui_service container..."
	DOCKER_BUILDKIT=1 $(DOCKER_CMD) compose build ui_service
	@echo "Build complete"

# Quick rebuild with aggressive caching
build-ui-quick:
	@echo "Quick building ui_service (with cache)..."
	DOCKER_BUILDKIT=1 $(DOCKER_CMD) compose build ui_service
	@echo "Build complete"

# Full clean build without cache
build-ui-clean:
	@echo "Clean building ui_service (no cache)..."
	$(DOCKER_CMD) compose build --no-cache ui_service
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
	@find ui_service -name "node_modules" -type d -exec rm -rf {} + 2>/dev/null || true
	@find ui_service -name ".next" -type d -exec rm -rf {} + 2>/dev/null || true
	@$(DOCKER_CMD) compose down --volumes --rmi local
	@echo "Clean complete"

health-check:
	@echo "Service Health Status:"
	@for port in 50051 50052 50054; do \
		grpc_health_probe -addr=localhost:$$port -connect-timeout=2s && \
		echo "Port $$port: Healthy" || echo "Port $$port: Unhealthy"; \
	done