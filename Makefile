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

# Colors for output (use printf for ANSI support on macOS)
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m
BOLD := \033[1m

# -----------------------------------------------------------------------------
# PHONY Declarations
# -----------------------------------------------------------------------------
.PHONY: help all build up down restart logs clean status status-verbose status-very-verbose status-guide health \
        proto-gen proto-gen-chroma proto-gen-llm proto-gen-shared \
        build-% restart-% logs-% shell-% status-% \
        provider-local provider-perplexity provider-openai provider-anthropic \
        test test-unit test-integration test-e2e \
        dev dev-ui dev-ui-local dev-backend query chat \
        db-reset db-backup db-restore \
        install-deps check-deps lint format \
        rebuild-orchestrator rebuild-all restart-orchestrator restart-all \
        verify-code logs-orch logs-tail logs-dump logs-clear

# ============================================================================
# HELP
# ============================================================================
help:
	@echo ""
	@printf '$(BOLD)$(CYAN)╔══════════════════════════════════════════════════════════════════╗$(RESET)\n'
	@printf '$(BOLD)$(CYAN)║         gRPC LLM Agent Framework - Command Reference             ║$(RESET)\n'
	@printf '$(BOLD)$(CYAN)╚══════════════════════════════════════════════════════════════════╝$(RESET)\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)🚀 Quick Start:$(RESET)\n'
	@printf '  $(CYAN)make start$(RESET)              - Build and start all services\n'
	@printf '  $(CYAN)make dev$(RESET)                - Start backend + UI in dev mode\n'
	@printf '  $(CYAN)make stop$(RESET)               - Stop all services\n'
	@printf '  $(CYAN)make status$(RESET)             - Containers + health + provider\n'
	@printf '  $(CYAN)make status verbose$(RESET)     - + port map, resources, images\n'
	@printf '  $(CYAN)make status very-verbose$(RESET) - + recursive file listing per container\n'
	@printf '  $(CYAN)make status guide$(RESET)       - How to test every component\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)🔧 Service Management:$(RESET)\n'
	@printf '  $(CYAN)make up$(RESET)                 - Start all services (detached)\n'
	@printf '  $(CYAN)make down$(RESET)               - Stop and remove containers\n'
	@printf '  $(CYAN)make restart$(RESET)            - Restart all services\n'
	@printf '  $(CYAN)make restart-<svc>$(RESET)      - Restart specific service\n'
	@printf '  $(CYAN)make logs$(RESET)               - Formatted rolling log (slog128)\n'
	@printf '  $(CYAN)make logs-<svc>$(RESET)         - Follow specific service logs\n'
	@printf '  $(CYAN)make logs-dump$(RESET)          - Print current slog128 buffer\n'
	@printf '  $(CYAN)make shell-<svc>$(RESET)        - Open shell in service container\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)🏗️  Build Commands:$(RESET)\n'
	@printf '  $(CYAN)make build$(RESET)              - Build all containers (parallel)\n'
	@printf '  $(CYAN)make build-<svc>$(RESET)        - Build specific service\n'
	@printf '  $(CYAN)make build-clean$(RESET)        - Full rebuild without cache\n'
	@printf '  $(CYAN)make rebuild$(RESET)            - Clean build + restart\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)🤖 LLM Provider Switching:$(RESET)\n'
	@printf '  $(CYAN)make provider-local$(RESET)     - Use local LLM (llama.cpp)\n'
	@printf '  $(CYAN)make provider-perplexity$(RESET) - Use Perplexity Sonar API\n'
	@printf '  $(CYAN)make provider-openai$(RESET)    - Use OpenAI GPT API\n'
	@printf '  $(CYAN)make provider-anthropic$(RESET) - Use Anthropic Claude API\n'
	@printf '  $(CYAN)make provider-openclaw$(RESET)  - Use OpenClaw Gateway (gpt-5.x)\n'
	@printf '  $(CYAN)make provider-status$(RESET)    - Show current provider config\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)💬 Chat & Query:$(RESET)\n'
	@printf '  $(CYAN)make query Q=\"...\"$(RESET)     - Send query to agent\n'
	@printf '  $(CYAN)make chat$(RESET)               - Interactive chat mode\n'
	@printf '  $(CYAN)make tool-test$(RESET)          - Test tool calling with sample query\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)🧪 Testing:$(RESET)\n'
	@printf '  $(CYAN)make test$(RESET)               - Run all tests\n'
	@printf '  $(CYAN)make test-unit$(RESET)          - Run unit tests only\n'
	@printf '  $(CYAN)make test-integration$(RESET)   - Run integration tests\n'
	@printf '  $(CYAN)make test-e2e$(RESET)           - Run end-to-end tests\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)📦 Proto Generation:$(RESET)\n'
	@printf '  $(CYAN)make proto-gen$(RESET)          - Generate all protobuf stubs\n'
	@printf '  $(CYAN)make proto-gen-shared$(RESET)   - Generate shared stubs only\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)🗄️  Database:$(RESET)\n'
	@printf '  $(CYAN)make db-reset$(RESET)           - Reset all databases\n'
	@printf '  $(CYAN)make db-backup$(RESET)          - Backup databases\n'
	@printf '  $(CYAN)make db-restore$(RESET)         - Restore from backup\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)🧹 Cleanup:$(RESET)\n'
	@printf '  $(CYAN)make clean$(RESET)              - Remove generated files\n'
	@printf '  $(CYAN)make clean-all$(RESET)          - Full cleanup (volumes, images)\n'
	@printf '  $(CYAN)make clean-logs$(RESET)         - Clear log files\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)📊 Monitoring:$(RESET)\n'
	@printf '  $(CYAN)make health$(RESET)             - Check all service health\n'
	@printf '  $(CYAN)make ps$(RESET)                 - Show running containers\n'
	@printf '  $(CYAN)make stats$(RESET)              - Show container resource usage\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)🔄 Cache Bust & Rebuild:$(RESET)\n'
	@printf '  $(CYAN)make rebuild-orchestrator$(RESET) - Force rebuild orchestrator (no cache)\n'
	@printf '  $(CYAN)make rebuild-all$(RESET)        - Force rebuild all services (no cache)\n'
	@printf '  $(CYAN)make restart-all$(RESET)        - Quick restart all services\n'
	@printf '  $(CYAN)make verify-code$(RESET)        - Verify code is current in container\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)📊 Observability:$(RESET)\n'
	@printf '  $(CYAN)make observability-up$(RESET)   - Start Prometheus, Grafana, OTel Collector\n'
	@printf '  $(CYAN)make observability-down$(RESET) - Stop observability stack\n'
	@printf '  $(CYAN)make observability-health$(RESET) - Check observability services health\n'
	@printf '  $(CYAN)make open-grafana$(RESET)       - Open Grafana in browser (localhost:3001)\n'
	@printf '  $(CYAN)make open-prometheus$(RESET)    - Open Prometheus in browser (localhost:9090)\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)🔗 OpenClaw Bridge (Bidirectional Integration):$(RESET)\n'
	@printf '  $(CYAN)make bridge-up$(RESET)          - Start MCP bridge service\n'
	@printf '  $(CYAN)make bridge-down$(RESET)        - Stop bridge service\n'
	@printf '  $(CYAN)make bridge-health$(RESET)      - Check bridge service health\n'
	@printf '  $(CYAN)make bridge-tools$(RESET)       - List tools exposed via MCP\n'
	@printf '  $(CYAN)make bridge-query Q=\"...\"$(RESET) - Test query through bridge\n'
	@printf '  $(CYAN)make openclaw-setup$(RESET)     - Full bidirectional setup\n'
	@echo ""
	@printf '$(BOLD)$(GREEN)📐 Prompt Flow (Visual Workflow & Evaluation):$(RESET)\n'
	@printf '  $(CYAN)make pf-run Q=\"...\"$(RESET)     - Run agent workflow with query\n'
	@printf '  $(CYAN)make pf-run-debug Q=\"...\"$(RESET) - Run with debug output\n'
	@printf '  $(CYAN)make pf-eval$(RESET)            - Run batch evaluation\n'
	@printf '  $(CYAN)make pf-serve$(RESET)           - Serve flow as API (port 8080)\n'
	@printf '  $(CYAN)make pf-trace$(RESET)           - Start trace UI (port 23333)\n'
	@printf '  $(CYAN)make pf-connections$(RESET)     - List registered connections\n'
	@printf '  $(CYAN)make pf-build$(RESET)           - Build Docker package\n'
	@echo ""
	@printf '$(BOLD)Services:$(RESET) orchestrator, llm_service, chroma_service, sandbox_service, registry_service, ui_service, bridge_service\n'
	@echo ""

# ============================================================================
# QUICK START
# ============================================================================
all: build up
	@printf '$(GREEN)✓ All services built and started$(RESET)\n'

start: build up status
	@echo ""
	@printf '$(GREEN)$(BOLD)✓ gRPC LLM Agent Framework is running!$(RESET)\n'
	@echo "  UI: http://localhost:$(PORT_UI)"
	@echo "  Orchestrator: localhost:$(PORT_ORCHESTRATOR)"

stop: down
	@printf '$(GREEN)✓ All services stopped$(RESET)\n'

# ============================================================================
# SERVICE MANAGEMENT
# ============================================================================
up:
	@printf '$(CYAN)Starting services...$(RESET)\n'
	@$(COMPOSE_CMD) up -d
	@printf '$(GREEN)✓ Services started$(RESET)\n'

down:
	@printf '$(CYAN)Stopping services...$(RESET)\n'
	@$(COMPOSE_CMD) down
	@printf '$(GREEN)✓ Services stopped$(RESET)\n'

restart: down up
	@printf '$(GREEN)✓ Services restarted$(RESET)\n'

# Pattern rule for restarting individual services
restart-%:
	@printf '$(CYAN)Restarting $*...$(RESET)\n'
	@$(COMPOSE_CMD) restart $*
	@printf '$(GREEN)✓ $* restarted$(RESET)\n'

# Pattern rule for service logs (live follow)
logs-%:
	@$(COMPOSE_CMD) logs -f --tail=80 $*

# Formatted rolling log — slog128 (128KB window, written to logs/)
LOG_DIR := $(PROJECT_ROOT)/logs
LOG_MAX_KB := 128

logs:
	@mkdir -p $(LOG_DIR)
	@printf '$(CYAN)Streaming logs → $(LOG_DIR)/services.log ($(LOG_MAX_KB)KB rolling window)$(RESET)\n'
	@printf '$(CYAN)Press Ctrl+C to stop$(RESET)\n'
	@$(COMPOSE_CMD) logs -f --tail=200 2>&1 | while IFS= read -r line; do \
		TS=$$(date '+%Y-%m-%d %H:%M:%S'); \
		SVC=$$(echo "$$line" | sed -n 's/^\([a-z_-]*\)[[:space:]]*|.*/\1/p'); \
		MSG=$$(echo "$$line" | sed 's/^[a-z_-]*[[:space:]]*|[[:space:]]*//' ); \
		FORMATTED="[$$TS] $$SVC | $$MSG"; \
		echo "$$FORMATTED"; \
		echo "$$FORMATTED" >> $(LOG_DIR)/services.log; \
		FSIZE=$$(stat -f%z $(LOG_DIR)/services.log 2>/dev/null || stat -c%s $(LOG_DIR)/services.log 2>/dev/null || echo 0); \
		MAX_BYTES=$$(($(LOG_MAX_KB) * 1024)); \
		if [ "$$FSIZE" -gt "$$MAX_BYTES" ] 2>/dev/null; then \
			tail -c $$MAX_BYTES $(LOG_DIR)/services.log > $(LOG_DIR)/services.log.tmp && \
			mv $(LOG_DIR)/services.log.tmp $(LOG_DIR)/services.log; \
		fi; \
	done

# Dump last 128KB of logs without following
logs-dump:
	@if [ -f $(LOG_DIR)/services.log ]; then \
		cat $(LOG_DIR)/services.log; \
	else \
		printf '$(YELLOW)No log file yet. Run make logs first.$(RESET)\n'; \
	fi

# Clear rolling log file
logs-clear:
	@rm -f $(LOG_DIR)/services.log
	@printf '$(GREEN)✓ Log file cleared$(RESET)\n'

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
	@printf '$(BOLD)$(CYAN)╔══════════════════════════════════════════════════════════════════╗$(RESET)\n'
	@printf '$(BOLD)$(CYAN)║               gRPC LLM Agent — System Status                    ║$(RESET)\n'
	@printf '$(BOLD)$(CYAN)╚══════════════════════════════════════════════════════════════════╝$(RESET)\n'
	@echo ""
	@printf '$(BOLD) ┌─────────────────────────────────────────────────────────────────┐$(RESET)\n'
	@printf '$(BOLD) │ 🐳 Containers                                                  │$(RESET)\n'
	@printf '$(BOLD) └─────────────────────────────────────────────────────────────────┘$(RESET)\n'
	@$(COMPOSE_CMD) ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null | while IFS= read -r line; do \
		if echo "$$line" | grep -qi "NAME"; then \
			printf '  $(BOLD)%-24s %-36s$(RESET)\n' "SERVICE" "STATUS"; \
			printf '  %-24s %-36s\n' "────────────────────────" "────────────────────────────────────"; \
		elif echo "$$line" | grep -qi "(healthy)"; then \
			SVC=$$(echo "$$line" | awk '{print $$1}'); \
			STATE=$$(echo "$$line" | cut -d' ' -f2-); \
			printf '  $(GREEN)●$(RESET) %-22s $(GREEN)%s$(RESET)\n' "$$SVC" "$$STATE"; \
		elif echo "$$line" | grep -qi "(unhealthy)"; then \
			SVC=$$(echo "$$line" | awk '{print $$1}'); \
			STATE=$$(echo "$$line" | cut -d' ' -f2-); \
			printf '  $(RED)●$(RESET) %-22s $(RED)%s$(RESET)\n' "$$SVC" "$$STATE"; \
		elif echo "$$line" | grep -qi "^[a-z]"; then \
			SVC=$$(echo "$$line" | awk '{print $$1}'); \
			STATE=$$(echo "$$line" | cut -d' ' -f2-); \
			printf '  $(YELLOW)◐$(RESET) %-22s $(YELLOW)%s$(RESET)\n' "$$SVC" "$$STATE"; \
		fi; \
	done
	@echo ""
	@printf '$(BOLD) ┌─────────────────────────────────────────────────────────────────┐$(RESET)\n'
	@printf '$(BOLD) │ 🔌 gRPC Health Probes                                          │$(RESET)\n'
	@printf '$(BOLD) └─────────────────────────────────────────────────────────────────┘$(RESET)\n'
	@for pair in "llm_service:$(PORT_LLM)" "chroma_service:$(PORT_CHROMA)" "orchestrator:$(PORT_ORCHESTRATOR)" "sandbox_service:$(PORT_SANDBOX)"; do \
		SVC=$$(echo "$$pair" | cut -d: -f1); PORT=$$(echo "$$pair" | cut -d: -f2); \
		if grpc_health_probe -addr=localhost:$$PORT -connect-timeout=2s 2>/dev/null; then \
			printf '  $(GREEN)●$(RESET) %-22s $(GREEN)healthy$(RESET)  :%s\n' "$$SVC" "$$PORT"; \
		else \
			printf '  $(RED)○$(RESET) %-22s $(RED)unreachable$(RESET)  :%s\n' "$$SVC" "$$PORT"; \
		fi; \
	done
	@for pair in "ui_service:5001" "dashboard_service:8001" "bridge_service:8100"; do \
		SVC=$$(echo "$$pair" | cut -d: -f1); PORT=$$(echo "$$pair" | cut -d: -f2); \
		if curl -sf http://localhost:$$PORT/health > /dev/null 2>&1 || curl -sf http://localhost:$$PORT > /dev/null 2>&1; then \
			printf '  $(GREEN)●$(RESET) %-22s $(GREEN)healthy$(RESET)  :%s\n' "$$SVC" "$$PORT"; \
		else \
			printf '  $(RED)○$(RESET) %-22s $(RED)unreachable$(RESET)  :%s\n' "$$SVC" "$$PORT"; \
		fi; \
	done
	@for pair in "prometheus:9090" "grafana:3001" "otel-collector:13133"; do \
		SVC=$$(echo "$$pair" | cut -d: -f1); PORT=$$(echo "$$pair" | cut -d: -f2); \
		if curl -sf http://localhost:$$PORT > /dev/null 2>&1 || curl -sf http://localhost:$$PORT/-/healthy > /dev/null 2>&1; then \
			printf '  $(GREEN)●$(RESET) %-22s $(GREEN)healthy$(RESET)  :%s\n' "$$SVC" "$$PORT"; \
		else \
			printf '  $(RED)○$(RESET) %-22s $(RED)unreachable$(RESET)  :%s\n' "$$SVC" "$$PORT"; \
		fi; \
	done
	@echo ""
	@printf '$(BOLD) ┌─────────────────────────────────────────────────────────────────┐$(RESET)\n'
	@printf '$(BOLD) │ 🤖 LLM Provider                                                │$(RESET)\n'
	@printf '$(BOLD) └─────────────────────────────────────────────────────────────────┘$(RESET)\n'
	@if [ -f $(ENV_FILE) ]; then \
		PROVIDER=$$(grep -E "^LLM_PROVIDER=" $(ENV_FILE) | cut -d= -f2); \
		MODEL=$$(grep -E "^LLM_PROVIDER_MODEL=" $(ENV_FILE) | cut -d= -f2); \
		printf '  Provider: $(BOLD)$(CYAN)%s$(RESET)\n' "$$PROVIDER"; \
		printf '  Model:    $(BOLD)%s$(RESET)\n' "$$MODEL"; \
		if [ "$$PROVIDER" = "openclaw" ]; then \
			URL=$$(grep -E "^OPENCLAW_URL=" $(ENV_FILE) | cut -d= -f2); \
			printf '  Gateway:  $(GREEN)%s$(RESET)\n' "$${URL:-http://host.docker.internal:18789/v1}"; \
		fi; \
	fi
	@echo ""

# Verbose status — full port map, resource usage, uptime
status-verbose: status
	@printf '$(BOLD) ┌─────────────────────────────────────────────────────────────────┐$(RESET)\n'
	@printf '$(BOLD) │ 🗺️  Port Map                                                    │$(RESET)\n'
	@printf '$(BOLD) └─────────────────────────────────────────────────────────────────┘$(RESET)\n'
	@printf '  $(BOLD)%-22s %-8s %-10s %-30s$(RESET)\n' "SERVICE" "PORT" "PROTOCOL" "URL"
	@printf '  %-22s %-8s %-10s %-30s\n' "──────────────────────" "────────" "──────────" "──────────────────────────────"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "orchestrator"       "50054" "gRPC"     "grpcurl -plaintext localhost:50054"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "llm_service"        "50051" "gRPC"     "grpcurl -plaintext localhost:50051"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "chroma_service"     "50052" "gRPC"     "grpcurl -plaintext localhost:50052"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "sandbox_service"    "50057" "gRPC"     "grpcurl -plaintext localhost:50057"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "ui_service"         "5001"  "HTTP"     "http://localhost:5001"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "dashboard_service"  "8001"  "HTTP"     "http://localhost:8001"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "bridge_service"     "8100"  "HTTP/MCP" "http://localhost:8100"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "grafana"            "3001"  "HTTP"     "http://localhost:3001"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "prometheus"         "9090"  "HTTP"     "http://localhost:9090"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "otel-collector"     "4317"  "OTLP"     "localhost:4317 (gRPC)"
	@printf '  %-22s %-8s %-10s $(CYAN)%-30s$(RESET)\n' "tempo"              "3200"  "HTTP"     "http://localhost:3200"
	@echo ""
	@printf '$(BOLD) ┌─────────────────────────────────────────────────────────────────┐$(RESET)\n'
	@printf '$(BOLD) │ 📊 Resource Usage                                               │$(RESET)\n'
	@printf '$(BOLD) └─────────────────────────────────────────────────────────────────┘$(RESET)\n'
	@$(DOCKER_CMD) stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" $$($(COMPOSE_CMD) ps -q 2>/dev/null) 2>/dev/null | \
		while IFS= read -r line; do printf '  %s\n' "$$line"; done
	@echo ""
	@printf '$(BOLD) ┌─────────────────────────────────────────────────────────────────┐$(RESET)\n'
	@printf '$(BOLD) │ 🏷️  Docker Images                                               │$(RESET)\n'
	@printf '$(BOLD) └─────────────────────────────────────────────────────────────────┘$(RESET)\n'
	@$(DOCKER_CMD) images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -E "grpc_llm|grafana|prom|tempo|otel" | \
		while IFS= read -r line; do printf '  %s\n' "$$line"; done
	@echo ""
	@printf '$(BOLD) ┌─────────────────────────────────────────────────────────────────┐$(RESET)\n'
	@printf '$(BOLD) │ 💾 Image Size Breakdown (largest first)                        │$(RESET)\n'
	@printf '$(BOLD) └─────────────────────────────────────────────────────────────────┘$(RESET)\n'
	@printf '  $(BOLD)%-35s %10s$(RESET)\n' "IMAGE" "SIZE"
	@printf '  %-35s %10s\n' "───────────────────────────────────" "──────────"
	@$(DOCKER_CMD) images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | \
		grep -E 'grpc_llm|grafana|prom|tempo|otel' | \
		awk -F'\t' '{ \
			raw = $$2; gsub(/[[:space:]]/, "", raw); \
			val = raw + 0; \
			if (raw ~ /GB/) val = val * 1024; \
			printf "%012.2f\t%s\t%s\n", val, $$1, raw; \
		}' | sort -rn | \
		while IFS=$$'\t' read -r sortkey name size; do \
			short=$$(echo "$$name" | sed 's/grpc_llm-//; s/:latest//'); \
			if echo "$$size" | grep -q 'GB'; then \
				printf '  $(RED)%-35s %10s$(RESET)\n' "$$short" "$$size"; \
			else \
				printf '  $(GREEN)%-35s %10s$(RESET)\n' "$$short" "$$size"; \
			 fi; \
		done
	@echo ""
	@# Flag stale images not in current compose
	@STALE=$$($(DOCKER_CMD) images --format '{{.Repository}}' | grep 'grpc_llm' | sort | \
		comm -23 - <($(COMPOSE_CMD) config --services 2>/dev/null | sed 's/^/grpc_llm-/' | sort) 2>/dev/null); \
	if [ -n "$$STALE" ]; then \
		printf '  $(YELLOW)⚠  Stale images (not in docker-compose):$(RESET)\n'; \
		for img in $$STALE; do \
			SZ=$$($(DOCKER_CMD) images --format '{{.Size}}' "$$img" 2>/dev/null | head -1); \
			printf '     $(YELLOW)%-35s %s$(RESET)\n' "$$img" "$$SZ"; \
		done; \
		printf '     $(YELLOW)Clean with: docker rmi %s$(RESET)\n' "$$STALE"; \
		echo ""; \
	fi

# Very-verbose status — per-container recursive file listing + largest files
status-very-verbose: status-verbose
	@printf '$(BOLD) ┌─────────────────────────────────────────────────────────────────┐$(RESET)\n'
	@printf '$(BOLD) │ 📂 Per-Container File System (top 15 largest files each)       │$(RESET)\n'
	@printf '$(BOLD) └─────────────────────────────────────────────────────────────────┘$(RESET)\n'
	@for svc in $$($(COMPOSE_CMD) config --services 2>/dev/null); do \
		CID=$$($(COMPOSE_CMD) ps -q $$svc 2>/dev/null); \
		if [ -z "$$CID" ]; then \
			printf '\n  $(YELLOW)◌ %-20s (not running — skipped)$(RESET)\n' "$$svc"; \
			continue; \
		fi; \
		TOTAL=$$($(DOCKER_CMD) exec $$CID du -sh / 2>/dev/null | awk '{print $$1}'); \
		if [ -z "$$TOTAL" ] || echo "$$TOTAL" | grep -qiE 'OCI|error|exec'; then \
			printf '\n  $(YELLOW)▸ %-20s  (minimal image — no shell)$(RESET)\n' "$$svc"; \
			continue; \
		fi; \
		printf '\n  $(BOLD)$(CYAN)▸ %-20s  total: %s$(RESET)\n' "$$svc" "$$TOTAL"; \
		printf '  %-50s %10s\n' "──────────────────────────────────────────────────" "──────────"; \
		$(DOCKER_CMD) exec $$CID sh -c 'find / -type f -exec du -k {} + 2>/dev/null | sort -rn | head -15' 2>/dev/null | \
			while read -r kb path; do \
				if [ "$$kb" -ge 1048576 ]; then \
					human=$$(awk "BEGIN{printf \"%.1fG\", $$kb/1048576}"); \
					printf '  $(RED)  %-48s %10s$(RESET)\n' "$$path" "$$human"; \
				elif [ "$$kb" -ge 1024 ]; then \
					human=$$(awk "BEGIN{printf \"%.1fM\", $$kb/1024}"); \
					if [ "$$kb" -ge 102400 ]; then \
						printf '  $(YELLOW)  %-48s %10s$(RESET)\n' "$$path" "$$human"; \
					else \
						printf '    %-48s %10s\n' "$$path" "$$human"; \
					fi; \
				else \
					printf '    %-48s %10sK\n' "$$path" "$$kb"; \
				fi; \
			done; \
	done
	@echo ""
	@printf '$(BOLD) ┌─────────────────────────────────────────────────────────────────┐$(RESET)\n'
	@printf '$(BOLD) │ 📁 Directory Tree (depth 3, /app only)                         │$(RESET)\n'
	@printf '$(BOLD) └─────────────────────────────────────────────────────────────────┘$(RESET)\n'
	@for svc in $$($(COMPOSE_CMD) config --services 2>/dev/null); do \
		CID=$$($(COMPOSE_CMD) ps -q $$svc 2>/dev/null); \
		if [ -z "$$CID" ]; then continue; fi; \
		printf '\n  $(BOLD)$(CYAN)▸ %s$(RESET)\n' "$$svc"; \
		if ! $(DOCKER_CMD) exec $$CID sh -c 'true' >/dev/null 2>&1; then \
			printf '    $(YELLOW)(minimal image — no shell)$(RESET)\n'; \
			continue; \
		fi; \
		$(DOCKER_CMD) exec $$CID sh -c 'if [ -d /app ]; then find /app -maxdepth 3 -type d | sort | head -40 | sed "s|^|    |"; else echo "    (no /app directory)"; fi' 2>/dev/null; \
	done
	@echo ""

# Quick usage guide for every component
status-guide:
	@echo ""
	@printf '$(BOLD)$(CYAN)╔══════════════════════════════════════════════════════════════════╗$(RESET)\n'
	@printf '$(BOLD)$(CYAN)║             Component Testing & Usage Guide                     ║$(RESET)\n'
	@printf '$(BOLD)$(CYAN)╚══════════════════════════════════════════════════════════════════╝$(RESET)\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 🧠 Orchestrator$(RESET) (gRPC :50054)\n'
	@printf '  List services:   grpcurl -plaintext localhost:50054 list\n'
	@printf '  Send query:      make query Q="What is 2+2?"\n'
	@printf '  Interactive:     make chat\n'
	@printf '  Logs:            make status orchestrator log\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 🤖 LLM Service$(RESET) (gRPC :50051)\n'
	@printf '  Health:          grpc_health_probe -addr=localhost:50051\n'
	@printf '  Switch provider: make provider-openai | make provider-anthropic\n'
	@printf '  Logs:            make status llm_service log\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 📚 Chroma Service$(RESET) (gRPC :50052)\n'
	@printf '  Health:          grpc_health_probe -addr=localhost:50052\n'
	@printf '  Logs:            make status chroma_service log\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 🔒 Sandbox Service$(RESET) (gRPC :50057)\n'
	@printf '  Health:          grpc_health_probe -addr=localhost:50057\n'
	@printf '  Logs:            make status sandbox_service log\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 🖥️  UI Service$(RESET) (HTTP :5001)\n'
	@printf '  Open:            open http://localhost:5001\n'
	@printf '  Dev mode:        make dev-ui-local\n'
	@printf '  Logs:            make status ui_service log\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 📊 Dashboard$(RESET) (HTTP :8001)\n'
	@printf '  Finance:         open http://localhost:8001\n'
	@printf '  API docs:        open http://localhost:8001/docs\n'
	@printf '  Health:          curl -s http://localhost:8001/health | python3 -m json.tool\n'
	@printf '  Logs:            make status dashboard_service log\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 🌉 MCP Bridge$(RESET) (HTTP :8100)\n'
	@printf '  Tools:           make bridge-tools\n'
	@printf '  Query:           make bridge-query Q="Hello"\n'
	@printf '  Logs:            make status bridge_service log\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 📈 Grafana$(RESET) (HTTP :3001)\n'
	@printf '  Open:            open http://localhost:3001  (admin/admin)\n'
	@printf '  Dashboards:      gRPC LLM folder → Overview, Health, Providers, Tools\n'
	@printf '  Logs:            make status grafana log\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 📡 Prometheus$(RESET) (HTTP :9090)\n'
	@printf '  Open:            open http://localhost:9090\n'
	@printf '  Targets:         open http://localhost:9090/targets\n'
	@printf '  Logs:            make status prometheus log\n'
	@echo ""
	@printf '$(BOLD)$(GREEN) 🧪 Testing$(RESET)\n'
	@printf '  All tests:       make test\n'
	@printf '  Unit:            make test-unit\n'
	@printf '  Integration:     make test-integration\n'
	@printf '  Evals:           make eval\n'
	@echo ""

# Per-service log viewer — make status <service> log
status-%:
	@SVC="$*"; \
	if echo "$$SVC" | grep -q " log$$"; then \
		SVC=$$(echo "$$SVC" | sed 's/ log$$//'); \
		$(COMPOSE_CMD) logs --tail=80 -f "$$SVC"; \
	else \
		printf '$(YELLOW)Unknown sub-command. Use: make status $$SVC log$(RESET)\n'; \
	fi

# ============================================================================
# BUILD COMMANDS
# ============================================================================
build:
	@printf '$(CYAN)Building all containers (parallel)...$(RESET)\n'
	@$(COMPOSE_CMD) build --parallel
	@printf '$(GREEN)✓ Build complete$(RESET)\n'

build-clean:
	@printf '$(CYAN)Building all containers (no cache)...$(RESET)\n'
	@$(COMPOSE_CMD) build --no-cache --parallel
	@printf '$(GREEN)✓ Clean build complete$(RESET)\n'

rebuild: build-clean restart
	@printf '$(GREEN)✓ Rebuild complete$(RESET)\n'

# Pattern rule for building individual services
build-%:
	@printf '$(CYAN)Building $*...$(RESET)\n'
	@$(COMPOSE_CMD) build $*
	@printf '$(GREEN)✓ $* built$(RESET)\n'

# Quick rebuild and restart for development
quick-%: build-% restart-%
	@printf '$(GREEN)✓ $* rebuilt and restarted$(RESET)\n'

# ============================================================================
# LLM PROVIDER MANAGEMENT
# ============================================================================
provider-status:
	@if [ -f $(ENV_FILE) ]; then \
		PROVIDER=$$(grep -E "^LLM_PROVIDER=" $(ENV_FILE) | cut -d= -f2); \
		MODEL=$$(grep -E "^LLM_PROVIDER_MODEL=" $(ENV_FILE) | cut -d= -f2); \
		printf '  Provider: $(BOLD)$(CYAN)%s$(RESET)  Model: $(BOLD)%s$(RESET)\n' "$$PROVIDER" "$$MODEL"; \
	fi

provider-local:
	@printf '$(CYAN)Switching to local LLM provider...$(RESET)\n'
	@sed -i '' 's/^LLM_PROVIDER=.*/LLM_PROVIDER=local/' $(ENV_FILE)
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=qwen2.5-3b-instruct/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@printf '$(GREEN)✓ Now using local LLM$(RESET)\n'
	@$(MAKE) --no-print-directory provider-status

provider-perplexity:
	@printf '$(CYAN)Switching to Perplexity provider...$(RESET)\n'
	@sed -i '' 's/^LLM_PROVIDER=.*/LLM_PROVIDER=perplexity/' $(ENV_FILE)
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=sonar-pro/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@printf '$(GREEN)✓ Now using Perplexity Sonar$(RESET)\n'
	@$(MAKE) --no-print-directory provider-status

provider-openai:
	@printf '$(CYAN)Switching to OpenAI provider...$(RESET)\n'
	@sed -i '' 's/^LLM_PROVIDER=.*/LLM_PROVIDER=openai/' $(ENV_FILE)
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=gpt-4o-mini/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@printf '$(GREEN)✓ Now using OpenAI$(RESET)\n'
	@$(MAKE) --no-print-directory provider-status

provider-anthropic:
	@printf '$(CYAN)Switching to Anthropic provider...$(RESET)\n'
	@sed -i '' 's/^LLM_PROVIDER=.*/LLM_PROVIDER=anthropic/' $(ENV_FILE)
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=claude-3-5-sonnet-20241022/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@printf '$(GREEN)✓ Now using Anthropic Claude$(RESET)\n'
	@$(MAKE) --no-print-directory provider-status

provider-openclaw:
	@printf '$(CYAN)Switching to OpenClaw Gateway provider...$(RESET)\n'
	@sed -i '' 's/^LLM_PROVIDER=.*/LLM_PROVIDER=openclaw/' $(ENV_FILE)
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=gpt-5.2/' $(ENV_FILE)
	@grep -q "^OPENCLAW_URL=" $(ENV_FILE) || echo "OPENCLAW_URL=http://host.docker.internal:18789/v1" >> $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@printf '$(GREEN)✓ Now using OpenClaw Gateway (gpt-5.2)$(RESET)\n'
	@$(MAKE) --no-print-directory provider-status

# Set custom model for current provider
set-model:
	@if [ -z "$(MODEL)" ]; then \
		echo "$(RED)Usage: make set-model MODEL=<model-name>$(RESET)"; \
		exit 1; \
	fi
	@sed -i '' 's/^LLM_PROVIDER_MODEL=.*/LLM_PROVIDER_MODEL=$(MODEL)/' $(ENV_FILE)
	@$(MAKE) --no-print-directory restart-orchestrator
	@printf '$(GREEN)✓ Model set to $(MODEL)$(RESET)\n'

# ============================================================================
# CHAT & QUERY COMMANDS
# ============================================================================
query:
	@if [ -z "$(Q)" ]; then \
		echo "$(RED)Usage: make query Q=\"your question here\"$(RESET)"; \
		exit 1; \
	fi
	@printf '$(CYAN)Querying agent...$(RESET)\n'
	@grpcurl -plaintext -d '{"user_query": "$(Q)", "debug_mode": true}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent 2>/dev/null | \
		jq -r '.finalAnswer // .error // "No response"' 2>/dev/null || \
		echo "$(RED)Error: Could not connect to orchestrator$(RESET)"

# Interactive chat mode
chat:
	@printf '$(BOLD)$(CYAN)Interactive Chat Mode$(RESET)\n'
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
	@printf '$(CYAN)Testing tool calling with commute query...$(RESET)\n'
	@grpcurl -plaintext -d '{"user_query": "How long will it take me to drive to the airport?", "debug_mode": true}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent | jq .

# Smoke test - run multiple test queries
smoke-test:
	@printf '$(BOLD)$(CYAN)Running Smoke Tests$(RESET)\n'
	@echo "─────────────────────────────────────────"
	@echo ""
	@printf '$(CYAN)1. Testing commute to office:$(RESET)\n'
	@grpcurl -plaintext -d '{"user_query": "How long to drive to the office?"}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent 2>/dev/null | \
		jq -r '.final_answer // .error // "FAILED"' || echo "$(RED)FAILED$(RESET)"
	@echo ""
	@printf '$(CYAN)2. Testing calendar:$(RESET)\n'
	@grpcurl -plaintext -d '{"user_query": "What is my schedule today?"}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent 2>/dev/null | \
		jq -r '.final_answer // .error // "FAILED"' || echo "$(RED)FAILED$(RESET)"
	@echo ""
	@printf '$(CYAN)3. Testing general question (no tool):$(RESET)\n'
	@grpcurl -plaintext -d '{"user_query": "What is 2 + 2?"}' \
		localhost:$(PORT_ORCHESTRATOR) agent.AgentService/QueryAgent 2>/dev/null | \
		jq -r '.final_answer // .error // "FAILED"' || echo "$(RED)FAILED$(RESET)"
	@echo ""
	@printf '$(GREEN)✓ Smoke tests complete$(RESET)\n'

# ============================================================================
# DEVELOPMENT MODE
# ============================================================================
dev: dev-backend dev-ui
	@printf '$(GREEN)✓ Development environment ready$(RESET)\n'

dev-backend:
	@printf '$(CYAN)Starting backend services...$(RESET)\n'
	@$(COMPOSE_CMD) up -d $(BACKEND_SERVICES)
	@printf '$(GREEN)✓ Backend services started$(RESET)\n'

dev-ui:
	@printf '$(CYAN)Starting UI in development mode...$(RESET)\n'
	@cd ui_service && npm run dev &
	@printf '$(GREEN)✓ UI dev server starting at http://localhost:3000$(RESET)\n'

dev-ui-local:
	@printf '$(CYAN)Starting local npm dev server (port 3000)...$(RESET)\n'
	@printf '$(YELLOW)Prerequisite: npm install in ui_service/$(RESET)\n'
	@if [ ! -d "ui_service/node_modules" ]; then \
		echo "$(RED)✗ node_modules not found. Run: cd ui_service && npm install$(RESET)"; \
		exit 1; \
	fi
	@cd ui_service && npm run dev

dev-ui-docker:
	@printf '$(CYAN)Starting UI service in Docker (port 5001)...$(RESET)\n'
	@$(COMPOSE_CMD) up -d ui_service
	@printf '$(GREEN)✓ UI service started at http://localhost:5001$(RESET)\n'

# Watch orchestrator logs during development
watch-orchestrator:
	@$(COMPOSE_CMD) logs -f orchestrator | grep --color=auto -E "Tool|ERROR|WARNING|tool_call|iteration"

# ============================================================================
# PROTO GENERATION
# ============================================================================
proto-gen: proto-gen-chroma proto-gen-llm proto-gen-shared
	@printf '$(GREEN)✓ All protobufs generated$(RESET)\n'

proto-gen-chroma:
	@printf '$(CYAN)Generating chroma protobuf stubs...$(RESET)\n'
	@python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=chroma_service \
		--grpc_python_out=chroma_service \
		$(PROTO_DIR)/chroma.proto
	@sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' chroma_service/*_pb2_grpc.py

proto-gen-llm:
	@printf '$(CYAN)Generating llm protobuf stubs...$(RESET)\n'
	@python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=llm_service \
		--grpc_python_out=llm_service \
		$(PROTO_DIR)/llm.proto
	@sed -i '' 's/^import \(.*\)_pb2 as/from . import \1_pb2 as/' llm_service/*_pb2_grpc.py

proto-gen-shared:
	@mkdir -p shared/generated
	@printf '$(CYAN)Generating shared protobuf stubs...$(RESET)\n'
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
	@printf '$(GREEN)✓ All tests complete$(RESET)\n'

test-unit:
	@printf '$(CYAN)Running unit tests...$(RESET)\n'
	@cd tests && python -m pytest unit/ -v --tb=short

test-integration:
	@printf '$(CYAN)Running integration tests...$(RESET)\n'
	@cd tests && python -m pytest integration/ -v --tb=short

test-e2e:
	@printf '$(CYAN)Running end-to-end tests...$(RESET)\n'
	@cd tests && python -m pytest integration/test_orchestrator_e2e.py -v

test-tools:
	@printf '$(CYAN)Running tool tests...$(RESET)\n'
	@cd tests && python -m pytest unit/test_builtin_tools.py -v

# ============================================================================
# HEALTH CHECKS (used internally, prefer `make status` for user-facing)
# ============================================================================
health:
	@for pair in "llm_service:$(PORT_LLM)" "chroma_service:$(PORT_CHROMA)" "orchestrator:$(PORT_ORCHESTRATOR)" "sandbox_service:$(PORT_SANDBOX)"; do \
		SVC=$${pair%%:*}; PORT=$${pair##*:}; \
		if grpc_health_probe -addr=localhost:$$PORT -connect-timeout=2s 2>/dev/null; then \
			printf '  $(GREEN)●$(RESET) %-20s $(GREEN)healthy$(RESET)\n' "$$SVC"; \
		else \
			printf '  $(RED)○$(RESET) %-20s $(RED)unreachable$(RESET)\n' "$$SVC"; \
		fi; \
	done

health-watch:
	@watch -n 5 '$(MAKE) --no-print-directory health'

# ============================================================================
# DATABASE MANAGEMENT
# ============================================================================
db-reset:
	@printf '$(YELLOW)⚠ This will delete all database data. Continue? [y/N]$(RESET)\n'
	@read ans && [ "$$ans" = "y" ] || (echo "Cancelled" && exit 1)
	@printf '$(CYAN)Resetting databases...$(RESET)\n'
	@rm -rf chroma_service/data/*
	@rm -rf data/*.sqlite
	@$(MAKE) --no-print-directory restart-chroma_service
	@printf '$(GREEN)✓ Databases reset$(RESET)\n'

db-backup:
	@printf '$(CYAN)Backing up databases...$(RESET)\n'
	@mkdir -p backups/$(shell date +%Y%m%d_%H%M%S)
	@cp -r chroma_service/data backups/$(shell date +%Y%m%d_%H%M%S)/chroma_data
	@cp -r data/*.sqlite backups/$(shell date +%Y%m%d_%H%M%S)/ 2>/dev/null || true
	@printf '$(GREEN)✓ Backup created in backups/$(shell date +%Y%m%d_%H%M%S)$(RESET)\n'

db-restore:
	@if [ -z "$(BACKUP)" ]; then \
		echo "$(RED)Usage: make db-restore BACKUP=<backup-dir>$(RESET)"; \
		echo "Available backups:"; \
		ls -la backups/ 2>/dev/null || echo "  No backups found"; \
		exit 1; \
	fi
	@printf '$(CYAN)Restoring from $(BACKUP)...$(RESET)\n'
	@cp -r $(BACKUP)/chroma_data/* chroma_service/data/
	@cp $(BACKUP)/*.sqlite data/ 2>/dev/null || true
	@$(MAKE) --no-print-directory restart
	@printf '$(GREEN)✓ Database restored$(RESET)\n'

# ============================================================================
# CLEANUP
# ============================================================================
clean:
	@printf '$(CYAN)Cleaning generated files...$(RESET)\n'
	@find . -name "*_pb2*.py" -delete 2>/dev/null || true
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@printf '$(GREEN)✓ Clean complete$(RESET)\n'

clean-docker:
	@printf '$(CYAN)Cleaning Docker resources...$(RESET)\n'
	@$(COMPOSE_CMD) down --volumes --remove-orphans
	@$(DOCKER_CMD) image prune -f
	@printf '$(GREEN)✓ Docker cleanup complete$(RESET)\n'

clean-ui:
	@printf '$(CYAN)Cleaning UI build artifacts...$(RESET)\n'
	@rm -rf ui_service/node_modules ui_service/.next ui_service/out
	@printf '$(GREEN)✓ UI cleanup complete$(RESET)\n'

clean-all: clean clean-docker clean-ui
	@printf '$(CYAN)Removing local images...$(RESET)\n'
	@$(COMPOSE_CMD) down --rmi local 2>/dev/null || true
	@printf '$(GREEN)✓ Full cleanup complete$(RESET)\n'

clean-logs:
	@printf '$(CYAN)Clearing log files...$(RESET)\n'
	@find . -name "*.log" -delete 2>/dev/null || true
	@$(DOCKER_CMD) system prune -f --volumes 2>/dev/null || true
	@printf '$(GREEN)✓ Logs cleared$(RESET)\n'

# ============================================================================
# DEPENDENCIES & SETUP
# ============================================================================
install-deps:
	@printf '$(CYAN)Installing dependencies...$(RESET)\n'
	@pip install grpcio-tools grpcio-health-checking
	@cd ui_service && npm install
	@printf '$(GREEN)✓ Dependencies installed$(RESET)\n'

check-deps:
	@printf '$(BOLD)$(CYAN)Dependency Check:$(RESET)\n'
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
	@printf '$(CYAN)Running linters...$(RESET)\n'
	@python -m flake8 orchestrator/ core/ tools/ --max-line-length=120 || true
	@cd ui_service && npm run lint 2>/dev/null || true
	@printf '$(GREEN)✓ Lint complete$(RESET)\n'

format:
	@printf '$(CYAN)Formatting code...$(RESET)\n'
	@python -m black orchestrator/ core/ tools/ --line-length=120 || true
	@cd ui_service && npm run format 2>/dev/null || true
	@printf '$(GREEN)✓ Format complete$(RESET)\n'

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

# ============================================================================
# Docker Cache Bust & Rebuild Targets
# ============================================================================

# Force rebuild orchestrator without cache
rebuild-orchestrator:
	@printf '$(CYAN)Removing old orchestrator image...$(RESET)\n'
	@$(DOCKER_CMD) rmi grpc_llm-orchestrator:latest -f 2>/dev/null || true
	@printf '$(CYAN)Building orchestrator without cache...$(RESET)\n'
	@$(COMPOSE_CMD) build --no-cache orchestrator
	@printf '$(CYAN)Recreating orchestrator container...$(RESET)\n'
	@$(COMPOSE_CMD) up -d --force-recreate orchestrator
	@printf '$(GREEN)✓ Done. Check logs with: make logs-orchestrator$(RESET)\n'

# Force rebuild all services without cache
rebuild-all:
	@printf '$(CYAN)Rebuilding all services without cache...$(RESET)\n'
	@$(COMPOSE_CMD) build --no-cache
	@$(COMPOSE_CMD) up -d --force-recreate
	@printf '$(GREEN)✓ Done. Check status with: make status$(RESET)\n'

# Quick restart (uses cache, faster)
restart-orchestrator:
	@$(COMPOSE_CMD) restart orchestrator

# Quick restart all services (alias for existing restart target)
restart-all: restart

# Verify code is current inside container
verify-code:
	@printf '$(CYAN)Checking orchestrator code version...$(RESET)\n'
	@$(DOCKER_CMD) exec orchestrator python -c "from tools.builtin.user_context import get_commute_time; print('$(GREEN)✓ user_context imported$(RESET)')" 2>/dev/null || echo "$(RED)✗ Import failed$(RESET)"
	@$(DOCKER_CMD) exec orchestrator python -c "from tools.registry import tool_registry; print(f'$(GREEN)✓ {len(tool_registry._tools)} tools registered$(RESET)')" 2>/dev/null || echo "$(RED)✗ Registry check failed$(RESET)"

# Tail orchestrator logs (convenience alias)
logs-orch:
	@$(COMPOSE_CMD) logs -f --tail=100 orchestrator

# Tail all logs with limited history
logs-tail:
	@$(COMPOSE_CMD) logs -f --tail=50

# ============================================================================
# Observability Stack Commands
# ============================================================================

# Start observability services only
observability-up:
	@printf '$(CYAN)Starting observability stack (Prometheus, Grafana, OTel Collector)...$(RESET)\n'
	@$(COMPOSE_CMD) up -d otel-collector prometheus grafana tempo
	@printf '$(GREEN)✓ Observability stack started$(RESET)\n'
	@echo "  Grafana:    http://localhost:3001 (admin/admin)"
	@echo "  Prometheus: http://localhost:9090"

# Stop observability services
observability-down:
	@printf '$(CYAN)Stopping observability stack...$(RESET)\n'
	@$(COMPOSE_CMD) stop otel-collector prometheus grafana tempo
	@printf '$(GREEN)✓ Observability stack stopped$(RESET)\n'

# View Grafana logs
logs-grafana:
	@$(COMPOSE_CMD) logs -f grafana

# View Prometheus logs
logs-prometheus:
	@$(COMPOSE_CMD) logs -f prometheus

# View OTel Collector logs
logs-otel:
	@$(COMPOSE_CMD) logs -f otel-collector

# Open Grafana in browser (macOS)
open-grafana:
	@open http://localhost:3001

# Open Prometheus in browser (macOS)
open-prometheus:
	@open http://localhost:9090

# Check observability health
observability-health:
	@printf '$(BOLD)$(CYAN)Observability Health:$(RESET)\n'
	@echo "─────────────────────────────────────────"
	@printf "  %-20s " "otel-collector:"; \
		(curl -s http://localhost:13133/ >/dev/null && echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"
	@printf "  %-20s " "prometheus:"; \
		(curl -s http://localhost:9090/-/healthy >/dev/null && echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"
	@printf "  %-20s " "grafana:"; \
		(curl -s http://localhost:3001/api/health >/dev/null && echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"

# ============================================================================
# Bridge Service Commands (OpenClaw ↔ gRPC Bidirectional Communication)
# ============================================================================

# Start bridge service only
bridge-up:
	@printf '$(CYAN)Starting bridge service (MCP server)...$(RESET)\n'
	@$(COMPOSE_CMD) up -d bridge_service
	@printf '$(GREEN)✓ Bridge service started at http://localhost:8100$(RESET)\n'

# Stop bridge service
bridge-down:
	@printf '$(CYAN)Stopping bridge service...$(RESET)\n'
	@$(COMPOSE_CMD) stop bridge_service
	@printf '$(GREEN)✓ Bridge service stopped$(RESET)\n'

# Rebuild bridge service
bridge-rebuild:
	@printf '$(CYAN)Rebuilding bridge service...$(RESET)\n'
	@$(COMPOSE_CMD) build --no-cache bridge_service
	@$(COMPOSE_CMD) up -d bridge_service
	@printf '$(GREEN)✓ Bridge service rebuilt and started$(RESET)\n'

# View bridge service logs
logs-bridge:
	@$(COMPOSE_CMD) logs -f bridge_service

# Check bridge service health
bridge-health:
	@printf '$(BOLD)$(CYAN)Bridge Service Health:$(RESET)\n'
	@echo "─────────────────────────────────────────"
	@printf "  %-20s " "bridge_service:"; \
		(curl -s http://localhost:8100/health >/dev/null && echo "$(GREEN)● healthy$(RESET)") || echo "$(RED)○ unhealthy$(RESET)"

# List available tools exposed via MCP
bridge-tools:
	@printf '$(CYAN)Fetching tools from bridge service...$(RESET)\n'
	@curl -s http://localhost:8100/tools | jq '.' 2>/dev/null || echo "$(RED)Bridge service not running$(RESET)"

# Test query through bridge
bridge-query:
	@if [ -z "$(Q)" ]; then \
		echo "$(RED)Usage: make bridge-query Q=\"your question here\"$(RESET)"; \
		exit 1; \
	fi
	@printf '$(CYAN)Sending query through bridge...$(RESET)\n'
	@curl -s -X POST http://localhost:8100/tools/query_agent \
		-H "Content-Type: application/json" \
		-d '{"arguments": {"query": "$(Q)"}}' | jq '.' 2>/dev/null || \
		echo "$(RED)Error: Could not connect to bridge service$(RESET)"

# Test service health through bridge
bridge-health-check:
	@printf '$(CYAN)Checking service health via bridge...$(RESET)\n'
	@curl -s -X POST http://localhost:8100/tools/get_service_health \
		-H "Content-Type: application/json" \
		-d '{"arguments": {}}' | jq '.' 2>/dev/null || \
		echo "$(RED)Error: Could not connect to bridge service$(RESET)"

# Test daily briefing
bridge-briefing:
	@printf '$(CYAN)Getting daily briefing via bridge...$(RESET)\n'
	@curl -s -X POST http://localhost:8100/tools/get_daily_briefing \
		-H "Content-Type: application/json" \
		-d '{"arguments": {"include_weather": true, "include_commute": true}}' | jq '.' 2>/dev/null || \
		echo "$(RED)Error: Could not connect to bridge service$(RESET)"

# Build OpenClaw skill package
skill-build:
	@printf '$(CYAN)Building OpenClaw skill package...$(RESET)\n'
	@cd clawdbot_integration/skills/grpc-llm-skill && npm install && npm run build
	@printf '$(GREEN)✓ Skill package built$(RESET)\n'

# Full OpenClaw bidirectional setup
openclaw-setup: bridge-up skill-build
	@echo ""
	@printf '$(GREEN)✓ OpenClaw bidirectional integration ready!$(RESET)\n'
	@echo ""
	@echo "  Bridge MCP Server:  http://localhost:8100"
	@echo "  OpenClaw Gateway:   http://localhost:18789"
	@echo ""
	@echo "  To test: make bridge-query Q=\"What services are available?\""

# ============================================================================
# PROMPT FLOW
# ============================================================================

# Run Prompt Flow agent workflow
pf-run:
	@printf '$(CYAN)Running Prompt Flow agent workflow...$(RESET)\n'
	@cd promptflow/flows/agent_workflow && pf flow test --flow . --inputs user_query="$(Q)" debug_mode=false

# Run Prompt Flow with debug mode
pf-run-debug:
	@printf '$(CYAN)Running Prompt Flow agent workflow (debug)...$(RESET)\n'
	@cd promptflow/flows/agent_workflow && pf flow test --flow . --inputs user_query="$(Q)" debug_mode=true

# Run batch evaluation
pf-eval:
	@printf '$(CYAN)Running Prompt Flow evaluation...$(RESET)\n'
	@cd promptflow/flows/evaluator && pf flow test --flow . --data ../../data/eval_cases.csv

# Serve Prompt Flow as API
pf-serve:
	@printf '$(CYAN)Starting Prompt Flow server on port 8080...$(RESET)\n'
	@cd promptflow/flows/agent_workflow && pf flow serve --source . --port 8080

# Show Prompt Flow trace UI
pf-trace:
	@printf '$(CYAN)Starting Prompt Flow trace UI...$(RESET)\n'
	@pf service start --port 23333

# Create OpenAI connection
pf-connection-openai:
	@printf '$(CYAN)Creating OpenAI connection...$(RESET)\n'
	@pf connection create --file promptflow/connections/openai.yaml --set api_key=$(OPENAI_API_KEY)

# Create Anthropic connection
pf-connection-anthropic:
	@printf '$(CYAN)Creating Anthropic connection...$(RESET)\n'
	@pf connection create --file promptflow/connections/anthropic.yaml --set api_key=$(ANTHROPIC_API_KEY)

# List connections
pf-connections:
	@printf '$(CYAN)Listing Prompt Flow connections...$(RESET)\n'
	@pf connection list

# Build Prompt Flow package
pf-build:
	@printf '$(CYAN)Building Prompt Flow package...$(RESET)\n'
	@cd promptflow/flows/agent_workflow && pf flow build --source . --output dist --format docker

# ============================================================================
# Docker Troubleshooting Guide
# ============================================================================
# | Symptom                      | Cause              | Fix                      |
# |------------------------------|--------------------|--------------------------|
# | Code changes not reflected   | Docker cache       | make rebuild-orchestrator|
# | "Module not found" error     | Stale build        | make rebuild-all         |
# | Tool returns old data        | Container restart  | make restart-orchestrator|
# | Service not responding       | Check logs         | make logs-orchestrator   |
# ============================================================================