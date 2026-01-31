# ============================================================================
# gRPC LLM Agent Framework - Makefile
# ============================================================================
# Comprehensive CLI orchestration for development, testing, and deployment
# Usage: make help
# ============================================================================

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
SHELL := /bin/bash
.DEFAULT_GOAL := help

# Project paths
PROJECT_ROOT := $(shell pwd)
PROTO_DIR := shared/proto
ENV_FILE := .env

# Service definitions
SERVICES := orchestrator llm_service chroma_service sandbox_service registry_service ui_service
CORE_SERVICES := orchestrator llm_service chroma_service sandbox_service registry_service
BACKEND_SERVICES := orchestrator llm_service chroma_service sandbox_service

# Docker configuration
DOCKER_CMD := $(shell which docker 2>/dev/null || echo /usr/local/bin/docker)
COMPOSE_CMD := $(DOCKER_CMD) compose
export PATH := /Applications/Docker.app/Contents/Resources/bin:$(PATH)
export DOCKER_BUILDKIT := 1

# gRPC ports
PORT_LLM := 50051
PORT_CHROMA := 50052
PORT_ORCHESTRATOR := 50054
PORT_REGISTRY := 50055
PORT_SANDBOX := 50057
PORT_UI := 3000

# Colors for output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m
BOLD := \033[1m

# -----------------------------------------------------------------------------
# PHONY Declarations
# -----------------------------------------------------------------------------
.PHONY: help all build up down restart logs clean status health \
        proto-gen proto-gen-chroma proto-gen-llm proto-gen-shared \
        build-% restart-% logs-% shell-% \
        provider-local provider-perplexity provider-openai provider-anthropic \
        test test-unit test-integration test-e2e \
        dev dev-ui dev-backend query chat \
        db-reset db-backup db-restore \
        install-deps check-deps lint format

# ============================================================================
# HELP
# ============================================================================
help:
	@echo ""
	@echo "$(BOLD)$(CYAN)╔══════════════════════════════════════════════════════════════════╗$(RESET)"
	@echo "$(BOLD)$(CYAN)║         gRPC LLM Agent Framework - Command Reference             ║$(RESET)"
	@echo "$(BOLD)$(CYAN)╚══════════════════════════════════════════════════════════════════╝$(RESET)"
	@echo ""
	@echo "$(BOLD)$(GREEN)🚀 Quick Start:$(RESET)"
	@echo "  $(CYAN)make start$(RESET)              - Build and start all services"
	@echo "  $(CYAN)make dev$(RESET)                - Start backend + UI in dev mode"
	@echo "  $(CYAN)make stop$(RESET)               - Stop all services"
	@echo "  $(CYAN)make status$(RESET)             - Show service status and health"
	@echo ""
	@echo "$(BOLD)$(GREEN)🔧 Service Management:$(RESET)"
	@echo "  $(CYAN)make up$(RESET)                 - Start all services (detached)"
	@echo "  $(CYAN)make down$(RESET)               - Stop and remove containers"
	@echo "  $(CYAN)make restart$(RESET)            - Restart all services"
	@echo "  $(CYAN)make restart-<svc>$(RESET)      - Restart specific service"
	@echo "  $(CYAN)make logs$(RESET)               - Follow all service logs"
	@echo "  $(CYAN)make logs-<svc>$(RESET)         - Follow specific service logs"
	@echo "  $(CYAN)make shell-<svc>$(RESET)        - Open shell in service container"
	@echo ""
	@echo "$(BOLD)$(GREEN)🏗️  Build Commands:$(RESET)"
	@echo "  $(CYAN)make build$(RESET)              - Build all containers (parallel)"
	@echo "  $(CYAN)make build-<svc>$(RESET)        - Build specific service"
	@echo "  $(CYAN)make build-clean$(RESET)        - Full rebuild without cache"
	@echo "  $(CYAN)make rebuild$(RESET)            - Clean build + restart"
	@echo ""
	@echo "$(BOLD)$(GREEN)🤖 LLM Provider Switching:$(RESET)"
	@echo "  $(CYAN)make provider-local$(RESET)     - Use local LLM (llama.cpp)"
	@echo "  $(CYAN)make provider-perplexity$(RESET) - Use Perplexity Sonar API"
	@echo "  $(CYAN)make provider-openai$(RESET)    - Use OpenAI GPT API"
	@echo "  $(CYAN)make provider-anthropic$(RESET) - Use Anthropic Claude API"
	@echo "  $(CYAN)make provider-status$(RESET)    - Show current provider config"
	@echo ""
	@echo "$(BOLD)$(GREEN)💬 Chat & Query:$(RESET)"
	@echo "  $(CYAN)make query Q=\"...\"$(RESET)     - Send query to agent"
	@echo "  $(CYAN)make chat$(RESET)               - Interactive chat mode"
	@echo "  $(CYAN)make tool-test$(RESET)          - Test tool calling with sample query"
	@echo ""
	@echo "$(BOLD)$(GREEN)🧪 Testing:$(RESET)"
	@echo "  $(CYAN)make test$(RESET)               - Run all tests"
	@echo "  $(CYAN)make test-unit$(RESET)          - Run unit tests only"
	@echo "  $(CYAN)make test-integration$(RESET)   - Run integration tests"
	@echo "  $(CYAN)make test-e2e$(RESET)           - Run end-to-end tests"
	@echo ""
	@echo "$(BOLD)$(GREEN)📦 Proto Generation:$(RESET)"
	@echo "  $(CYAN)make proto-gen$(RESET)          - Generate all protobuf stubs"
	@echo "  $(CYAN)make proto-gen-shared$(RESET)   - Generate shared stubs only"
	@echo ""
	@echo "$(BOLD)$(GREEN)🗄️  Database:$(RESET)"
	@echo "  $(CYAN)make db-reset$(RESET)           - Reset all databases"
	@echo "  $(CYAN)make db-backup$(RESET)          - Backup databases"
	@echo "  $(CYAN)make db-restore$(RESET)         - Restore from backup"
	@echo ""
	@echo "$(BOLD)$(GREEN)🧹 Cleanup:$(RESET)"
	@echo "  $(CYAN)make clean$(RESET)              - Remove generated files"
	@echo "  $(CYAN)make clean-all$(RESET)          - Full cleanup (volumes, images)"
	@echo "  $(CYAN)make clean-logs$(RESET)         - Clear log files"
	@echo ""
	@echo "$(BOLD)$(GREEN)📊 Monitoring:$(RESET)"
	@echo "  $(CYAN)make health$(RESET)             - Check all service health"
	@echo "  $(CYAN)make ps$(RESET)                 - Show running containers"
	@echo "  $(CYAN)make stats$(RESET)              - Show container resource usage"
	@echo ""
	@echo "$(BOLD)Services:$(RESET) orchestrator, llm_service, chroma_service, sandbox_service, registry_service, ui_service"
	@echo ""

# ============================================================================
# QUICK START
# ============================================================================
all: build up
	@echo "$(GREEN)✓ All services built and started$(RESET)"

start: build up status
	@echo ""
	@echo "$(GREEN)$(BOLD)✓ gRPC LLM Agent Framework is running!$(RESET)"
	@echo "  UI: http://localhost:$(PORT_UI)"
	@echo "  Orchestrator: localhost:$(PORT_ORCHESTRATOR)"

stop: down
	@echo "$(GREEN)✓ All services stopped$(RESET)"

# ============================================================================
# SERVICE MANAGEMENT
# ============================================================================
up:
	@echo "$(CYAN)Starting services...$(RESET)"
	@$(COMPOSE_CMD) up -d
	@echo "$(GREEN)✓ Services started$(RESET)"

down:
	@echo "$(CYAN)Stopping services...$(RESET)"
	@$(COMPOSE_CMD) down
	@echo "$(GREEN)✓ Services stopped$(RESET)"

restart: down up
	@echo "$(GREEN)✓ Services restarted$(RESET)"

# Pattern rule for restarting individual services
restart-%:
	@echo "$(CYAN)Restarting $*...$(RESET)"
	@$(COMPOSE_CMD) restart $*
	@echo "$(GREEN)✓ $* restarted$(RESET)"

# Pattern rule for service logs
logs-%:
	@$(COMPOSE_CMD) logs -f $*

logs:
	@$(COMPOSE_CMD) logs -f

# Pattern rule for shell access
shell-%:
	@$(COMPOSE_CMD) exec $* /bin/sh

# Show container status
ps:
	@$(COMPOSE_CMD) ps -a

# Show resource stats
stats:
	@$(DOCKER_CMD) stats --no-stream $(shell $(COMPOSE_CMD) ps -q)

status:
	@echo ""
	@echo "$(BOLD)$(CYAN)Service Status:$(RESET)"
	@echo "─────────────────────────────────────────"
	@$(COMPOSE_CMD) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
	@echo ""
	@$(MAKE) --no-print-directory health
	@echo ""
	@$(MAKE) --no-print-directory provider-status

# ============================================================================
# BUILD COMMANDS
# ============================================================================
build:
	@echo "$(CYAN)Building all containers (parallel)...$(RESET)"
	@$(COMPOSE_CMD) build --parallel
	@echo "$(GREEN)✓ Build complete$(RESET)"

build-clean:
	@echo "$(CYAN)Building all containers (no cache)...$(RESET)"
	@$(COMPOSE_CMD) build --no-cache --parallel
	@echo "$(GREEN)✓ Clean build complete$(RESET)"

rebuild: build-clean restart
	@echo "$(GREEN)✓ Rebuild complete$(RESET)"

# Pattern rule for building individual services
build-%:
	@echo "$(CYAN)Building $*...$(RESET)"
	@$(COMPOSE_CMD) build $*
	@echo "$(GREEN)✓ $* built$(RESET)"

# Quick rebuild and restart for development
quick-%: build-% restart-%
	@echo "$(GREEN)✓ $* rebuilt and restarted$(RESET)"

# ============================================================================
# LLM PROVIDER MANAGEMENT
# ============================================================================
provider-status:
	@echo "$(BOLD)$(CYAN)LLM Provider Configuration:$(RESET)"
	@echo "─────────────────────────────────────────"
	@if [ -f $(ENV_FILE) ]; then \
		PROVIDER=$$(grep -E "^LLM_PROVIDER=" $(ENV_FILE) | cut -d= -f2); \
		MODEL=$$(grep -E "^LLM_PROVIDER_MODEL=" $(ENV_FILE) | cut -d= -f2); \
		echo "  Provider: $(BOLD)$$PROVIDER$(RESET)"; \
		echo "  Model:    $(BOLD)$$MODEL$(RESET)"; \
		if [ "$$PROVIDER" = "perplexity" ]; then \
			KEY=$$(grep -E "^PERPLEXITY_API_KEY=" $(ENV_FILE) | cut -d= -f2); \
			if [ -n "$$KEY" ]; then echo "  API Key:  $(GREEN)configured$(RESET)"; else echo "  API Key:  $(RED)missing$(RESET)"; fi; \
		elif [ "$$PROVIDER" = "openai" ]; then \
			KEY=$$(grep -E "^OPENAI_API_KEY=" $(ENV_FILE) | cut -d= -f2); \
			if [ -n "$$KEY" ]; then echo "  API Key:  $(GREEN)configured$(RESET)"; else echo "  API Key:  $(RED)missing$(RESET)"; fi; \
		elif [ "$$PROVIDER" = "anthropic" ]; then \
			KEY=$$(grep -E "^ANTHROPIC_API_KEY=" $(ENV_FILE) | cut -d= -f2); \
			if [ -n "$$KEY" ]; then echo "  API Key:  $(GREEN)configured$(RESET)"; else echo "  API Key:  $(RED)missing$(RESET)"; fi; \
		fi; \
	else \
		echo "  $(RED)No .env file found$(RESET)"; \
	fi

provider-local:
	@echo "$(CYAN)Switching to local LLM provider...$(RESET)"
	@sed -i '' 's/^LLM_PROVIDER=.*/LLM_PROVIDER=local/' $(ENV_FILE)
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=qwen2.5-3b-instruct/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@echo "$(GREEN)✓ Now using local LLM$(RESET)"
	@$(MAKE) --no-print-directory provider-status

provider-perplexity:
	@echo "$(CYAN)Switching to Perplexity provider...$(RESET)"
	@sed -i '' 's/^LLM_PROVIDER=.*/LLM_PROVIDER=perplexity/' $(ENV_FILE)
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=sonar-pro/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@echo "$(GREEN)✓ Now using Perplexity Sonar$(RESET)"
	@$(MAKE) --no-print-directory provider-status

provider-openai:
	@echo "$(CYAN)Switching to OpenAI provider...$(RESET)"
	@sed -i '' 's/^LLM_PROVIDER=.*/LLM_PROVIDER=openai/' $(ENV_FILE)
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=gpt-4o-mini/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@echo "$(GREEN)✓ Now using OpenAI$(RESET)"
	@$(MAKE) --no-print-directory provider-status

provider-anthropic:
	@echo "$(CYAN)Switching to Anthropic provider...$(RESET)"
	@sed -i '' 's/^LLM_PROVIDER=.*/LLM_PROVIDER=anthropic/' $(ENV_FILE)
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=claude-3-5-sonnet-20241022/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@echo "$(GREEN)✓ Now using Anthropic Claude$(RESET)"
	@$(MAKE) --no-print-directory provider-status

# Set custom model for current provider
set-model:
	@if [ -z "$(MODEL)" ]; then \
		echo "$(RED)Usage: make set-model MODEL=<model-name>$(RESET)"; \
		exit 1; \
	fi
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=$(MODEL)/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@echo "$(GREEN)✓ Model set to $(MODEL)$(RESET)"

# ============================================================================
# CHAT & QUERY COMMANDS
# ============================================================================
query:
	@if [ -z "$(Q)" ]; then \
		echo "$(RED)Usage: make query Q=\"your question here\"$(RESET)"; \
		exit 1; \
	fi
	@echo "$(CYAN)Querying agent...$(RESET)"
	@grpcurl -plaintext -d '{"user_query": "$(Q)", "debug_mode": true}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent 2>/dev/null | \
		jq -r '.finalAnswer // .error // "No response"' 2>/dev/null || \
		echo "$(RED)Error: Could not connect to orchestrator$(RESET)"

# Interactive chat mode
chat:
	@echo "$(BOLD)$(CYAN)Interactive Chat Mode$(RESET)"
	@echo "Type your message and press Enter. Type 'exit' to quit."
	@echo "─────────────────────────────────────────"
	@while true; do \
		printf "$(GREEN)You:$(RESET) "; \
		read input; \
		if [ "$$input" = "exit" ] || [ "$$input" = "quit" ]; then \
			echo "$(CYAN)Goodbye!$(RESET)"; \
			break; \
		fi; \
		echo "$(CYAN)Agent:$(RESET)"; \
		grpcurl -plaintext -d "{\"user_query\": \"$$input\"}" \
			localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent 2>/dev/null | \
			jq -r '.finalAnswer // .error // "No response"' 2>/dev/null || \
			echo "$(RED)Error connecting$(RESET)"; \
		echo ""; \
	done

# Test tool calling
tool-test:
	@echo "$(CYAN)Testing tool calling with commute query...$(RESET)"
	@grpcurl -plaintext -d '{"user_query": "How long will it take me to drive to the airport?", "debug_mode": true}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent | jq .

# Smoke test - run multiple test queries
smoke-test:
	@echo "$(BOLD)$(CYAN)Running Smoke Tests$(RESET)"
	@echo "─────────────────────────────────────────"
	@echo ""
	@echo "$(CYAN)1. Testing commute to office:$(RESET)"
	@grpcurl -plaintext -d '{"user_query": "How long to drive to the office?"}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent 2>/dev/null | \
		jq -r '.final_answer // .error // "FAILED"' || echo "$(RED)FAILED$(RESET)"
	@echo ""
	@echo "$(CYAN)2. Testing calendar:$(RESET)"
	@grpcurl -plaintext -d '{"user_query": "What is my schedule today?"}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent 2>/dev/null | \
		jq -r '.final_answer // .error // "FAILED"' || echo "$(RED)FAILED$(RESET)"
	@echo ""
	@echo "$(CYAN)3. Testing general question (no tool):$(RESET)"
	@grpcurl -plaintext -d '{"user_query": "What is 2 + 2?"}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent 2>/dev/null | \
		jq -r '.final_answer // .error // "FAILED"' || echo "$(RED)FAILED$(RESET)"
	@echo ""
	@echo "$(GREEN)✓ Smoke tests complete$(RESET)"

# ============================================================================
# DEVELOPMENT MODE
# ============================================================================
dev: dev-backend dev-ui
	@echo "$(GREEN)✓ Development environment ready$(RESET)"

dev-backend:
	@echo "$(CYAN)Starting backend services...$(RESET)"
	@$(COMPOSE_CMD) up -d $(BACKEND_SERVICES)
	@echo "$(GREEN)✓ Backend services started$(RESET)"

dev-ui:
	@echo "$(CYAN)Starting UI in development mode...$(RESET)"
	@cd ui_service && npm run dev &
	@echo "$(GREEN)✓ UI dev server starting at http://localhost:3000$(RESET)"

dev-ui-docker:
	@echo "$(CYAN)Starting UI service in Docker...$(RESET)"
	@$(COMPOSE_CMD) up -d ui_service
	@echo "$(GREEN)✓ UI service started$(RESET)"

# Watch orchestrator logs during development
watch-orchestrator:
	@$(COMPOSE_CMD) logs -f orchestrator | grep --color=auto -E "Tool|ERROR|WARNING|tool_call|iteration"

# ============================================================================
# PROTO GENERATION
# ============================================================================
proto-gen: proto-gen-chroma proto-gen-llm proto-gen-shared
	@echo "$(GREEN)✓ All protobufs generated$(RESET)"

proto-gen-chroma:
	@echo "$(CYAN)Generating chroma protobuf stubs...$(RESET)"
	@python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=chroma_service \
		--grpc_python_out=chroma_service \
		$(PROTO_DIR)/chroma.proto
	@sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' chroma_service/*_pb2_grpc.py

proto-gen-llm:
	@echo "$(CYAN)Generating llm protobuf stubs...$(RESET)"
	@python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=llm_service \
		--grpc_python_out=llm_service \
		$(PROTO_DIR)/llm.proto
	@sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' llm_service/*_pb2_grpc.py

proto-gen-shared:
	@mkdir -p shared/generated
	@echo "$(CYAN)Generating shared protobuf stubs...$(RESET)"
	@python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=shared/generated \
		--grpc_python_out=shared/generated \
		$(PROTO_DIR)/llm.proto \
		$(PROTO_DIR)/chroma.proto \
		$(PROTO_DIR)/agent.proto \
		$(PROTO_DIR)/registry.proto \
		$(PROTO_DIR)/worker.proto \
		$(PROTO_DIR)/sandbox.proto
	@sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' shared/generated/*_pb2_grpc.py

# ============================================================================
# TESTING
# ============================================================================
test: test-unit test-integration
	@echo "$(GREEN)✓ All tests complete$(RESET)"

test-unit:
	@echo "$(CYAN)Running unit tests...$(RESET)"
	@cd tests && python -m pytest unit/ -v --tb=short

test-integration:
	@echo "$(CYAN)Running integration tests...$(RESET)"
	@cd tests && python -m pytest integration/ -v --tb=short

test-e2e:
	@echo "$(CYAN)Running end-to-end tests...$(RESET)"
	@cd tests && python -m pytest integration/test_orchestrator_e2e.py -v

test-tools:
	@echo "$(CYAN)Running tool tests...$(RESET)"
	@cd tests && python -m pytest unit/test_builtin_tools.py -v

# ============================================================================
# HEALTH CHECKS
# ============================================================================
health:
	@echo "$(BOLD)$(CYAN)Service Health:$(RESET)"
	@echo "─────────────────────────────────────────"
	@printf "  %-20s " "llm_service:"; \
		(grpc_health_probe -addr=localhost:$(PORT_LLM) -connect-timeout=2s 2>/dev/null && \
		echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"
	@printf "  %-20s " "chroma_service:"; \
		(grpc_health_probe -addr=localhost:$(PORT_CHROMA) -connect-timeout=2s 2>/dev/null && \
		echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"
	@printf "  %-20s " "orchestrator:"; \
		(grpc_health_probe -addr=localhost:$(PORT_ORCHESTRATOR) -connect-timeout=2s 2>/dev/null && \
		echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"
	@printf "  %-20s " "registry_service:"; \
		(grpc_health_probe -addr=localhost:$(PORT_REGISTRY) -connect-timeout=2s 2>/dev/null && \
		echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"
	@printf "  %-20s " "sandbox_service:"; \
		(grpc_health_probe -addr=localhost:$(PORT_SANDBOX) -connect-timeout=2s 2>/dev/null && \
		echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"
	@printf "  %-20s " "ui_service:"; \
		(curl -s http://localhost:$(PORT_UI) > /dev/null && \
		echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"

health-watch:
	@watch -n 5 '$(MAKE) --no-print-directory health'

# ============================================================================
# DATABASE MANAGEMENT
# ============================================================================
db-reset:
	@echo "$(YELLOW)⚠ This will delete all database data. Continue? [y/N]$(RESET)"
	@read ans && [ "$$ans" = "y" ] || (echo "Cancelled" && exit 1)
	@echo "$(CYAN)Resetting databases...$(RESET)"
	@rm -rf chroma_service/data/*
	@rm -rf data/*.sqlite
	@$(MAKE) --no-print-directory restart-chroma_service
	@echo "$(GREEN)✓ Databases reset$(RESET)"

db-backup:
	@echo "$(CYAN)Backing up databases...$(RESET)"
	@mkdir -p backups/$(shell date +%Y%m%d_%H%M%S)
	@cp -r chroma_service/data backups/$(shell date +%Y%m%d_%H%M%S)/chroma_data
	@cp -r data/*.sqlite backups/$(shell date +%Y%m%d_%H%M%S)/ 2>/dev/null || true
	@echo "$(GREEN)✓ Backup created in backups/$(shell date +%Y%m%d_%H%M%S)$(RESET)"

db-restore:
	@if [ -z "$(BACKUP)" ]; then \
		echo "$(RED)Usage: make db-restore BACKUP=<backup-dir>$(RESET)"; \
		echo "Available backups:"; \
		ls -la backups/ 2>/dev/null || echo "  No backups found"; \
		exit 1; \
	fi
	@echo "$(CYAN)Restoring from $(BACKUP)...$(RESET)"
	@cp -r $(BACKUP)/chroma_data/* chroma_service/data/
	@cp $(BACKUP)/*.sqlite data/ 2>/dev/null || true
	@$(MAKE) --no-print-directory restart
	@echo "$(GREEN)✓ Database restored$(RESET)"

# ============================================================================
# CLEANUP
# ============================================================================
clean:
	@echo "$(CYAN)Cleaning generated files...$(RESET)"
	@find . -name "*_pb2*.py" -delete 2>/dev/null || true
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Clean complete$(RESET)"

clean-docker:
	@echo "$(CYAN)Cleaning Docker resources...$(RESET)"
	@$(COMPOSE_CMD) down --volumes --remove-orphans
	@$(DOCKER_CMD) image prune -f
	@echo "$(GREEN)✓ Docker cleanup complete$(RESET)"

clean-ui:
	@echo "$(CYAN)Cleaning UI build artifacts...$(RESET)"
	@rm -rf ui_service/node_modules ui_service/.next ui_service/out
	@echo "$(GREEN)✓ UI cleanup complete$(RESET)"

clean-all: clean clean-docker clean-ui
	@echo "$(CYAN)Removing local images...$(RESET)"
	@$(COMPOSE_CMD) down --rmi local 2>/dev/null || true
	@echo "$(GREEN)✓ Full cleanup complete$(RESET)"

clean-logs:
	@echo "$(CYAN)Clearing log files...$(RESET)"
	@find . -name "*.log" -delete 2>/dev/null || true
	@$(DOCKER_CMD) system prune -f --volumes 2>/dev/null || true
	@echo "$(GREEN)✓ Logs cleared$(RESET)"

# ============================================================================
# DEPENDENCIES & SETUP
# ============================================================================
install-deps:
	@echo "$(CYAN)Installing dependencies...$(RESET)"
	@pip install grpcio-tools grpcio-health-checking
	@cd ui_service && npm install
	@echo "$(GREEN)✓ Dependencies installed$(RESET)"

check-deps:
	@echo "$(BOLD)$(CYAN)Dependency Check:$(RESET)"
	@echo "─────────────────────────────────────────"
	@printf "  %-20s " "docker:"; \
		(command -v docker >/dev/null && echo "$(GREEN)✓ installed$(RESET)") || echo "$(RED)✗ missing$(RESET)"
	@printf "  %-20s " "docker-compose:"; \
		(docker compose version >/dev/null 2>&1 && echo "$(GREEN)✓ installed$(RESET)") || echo "$(RED)✗ missing$(RESET)"
	@printf "  %-20s " "grpcurl:"; \
		(command -v grpcurl >/dev/null && echo "$(GREEN)✓ installed$(RESET)") || echo "$(RED)✗ missing$(RESET)"
	@printf "  %-20s " "grpc_health_probe:"; \
		(command -v grpc_health_probe >/dev/null && echo "$(GREEN)✓ installed$(RESET)") || echo "$(RED)✗ missing$(RESET)"
	@printf "  %-20s " "python:"; \
		(command -v python >/dev/null && echo "$(GREEN)✓ installed$(RESET)") || echo "$(RED)✗ missing$(RESET)"
	@printf "  %-20s " "node:"; \
		(command -v node >/dev/null && echo "$(GREEN)✓ installed$(RESET)") || echo "$(RED)✗ missing$(RESET)"
	@printf "  %-20s " "jq:"; \
		(command -v jq >/dev/null && echo "$(GREEN)✓ installed$(RESET)") || echo "$(RED)✗ missing$(RESET)"

# ============================================================================
# CODE QUALITY
# ============================================================================
lint:
	@echo "$(CYAN)Running linters...$(RESET)"
	@python -m flake8 orchestrator/ core/ tools/ --max-line-length=120 || true
	@cd ui_service && npm run lint 2>/dev/null || true
	@echo "$(GREEN)✓ Lint complete$(RESET)"

format:
	@echo "$(CYAN)Formatting code...$(RESET)"
	@python -m black orchestrator/ core/ tools/ --line-length=120 || true
	@cd ui_service && npm run format 2>/dev/null || true
	@echo "$(GREEN)✓ Format complete$(RESET)"

# ============================================================================
# UTILITY ALIASES
# ============================================================================
# Short aliases for common commands
r: restart
l: logs
s: status
h: health
b: build
u: up
d: down
q: query
c: chat