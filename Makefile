# Environment setup
PROTO_DIR := shared/proto
SERVICES := agent_service chromadb_service llm_service tool_service

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
	done
	@echo "Protobuf generation complete"

build:
	@echo "Building Docker containers..."
	docker-compose build --parallel
	@echo "Build complete"

up:
	@echo "Starting services..."
	docker-compose up --detach

down:
	@echo "Stopping services..."
	docker-compose down

logs:
	docker-compose logs -f

clean:
	@echo "Cleaning generated files..."
	@find . -name "*_pb2*.py" -delete
	@docker-compose down --volumes --rmi local
	@echo "Clean complete"

health-check:
	@echo "Service Health Status:"
	@for port in 50051 50052 50053 50054; do \
		grpc_health_probe -addr=localhost:$$port -connect-timeout=2s && \
		echo "Port $$port: Healthy" || echo "Port $$port: Unhealthy"; \
	done