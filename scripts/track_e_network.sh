#!/bin/bash
# Track E: Network Tasks - gRPC Health, Service Discovery
# Skill: network_engineer.md

set -e
cd "$(dirname "$0")/.."

echo "═══════════════════════════════════════════════════════════"
echo "  Track E: Network & Service Mesh"
echo "═══════════════════════════════════════════════════════════"

# E1. gRPC Reflection Health
echo ""
echo "▶ E1. gRPC Reflection & Health Status"
echo "─────────────────────────────────────────────────────────────"

# Test each gRPC service
GRPC_SERVICES=(
    "orchestrator:50054"
    "llm_service:50051"
    "chroma_service:50052"
    "registry_service:50053"
    "sandbox_service:50055"
)

for svc_port in "${GRPC_SERVICES[@]}"; do
    svc="${svc_port%%:*}"
    port="${svc_port##*:}"
    echo ""
    echo "  Testing $svc (port $port):"
    
    # Test reflection
    if grpcurl -plaintext localhost:$port list 2>/dev/null | head -1; then
        echo "    ✅ gRPC reflection working"
    else
        echo "    ❌ gRPC reflection NOT working or service not running"
    fi
done

# E2. Service Discovery Documentation
echo ""
echo "▶ E2. Service Discovery Status"
echo "─────────────────────────────────────────────────────────────"

# Check if network documentation exists
if grep -q "Network\|Port\|Service" RUNBOOK_DOCKER.md 2>/dev/null; then
    echo "  ✅ Network info exists in RUNBOOK_DOCKER.md"
else
    echo "  ❌ Network documentation missing from RUNBOOK_DOCKER.md"
fi

# Show current port mappings from docker-compose
echo ""
echo "  Current port mappings from docker-compose.yaml:"
grep -E "^\s+ports:" -A2 docker-compose.yaml 2>/dev/null | grep -E "[0-9]+:[0-9]+" | head -10 || echo "    Could not parse ports"

# Network map
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Network Map (Service → Port → Protocol)"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  ┌─────────────────────┬───────┬──────────┬─────────────────┐"
echo "  │ Service             │ Port  │ Protocol │ Internal DNS    │"
echo "  ├─────────────────────┼───────┼──────────┼─────────────────┤"
echo "  │ orchestrator        │ 50054 │ gRPC     │ orchestrator    │"
echo "  │ llm_service         │ 50051 │ gRPC     │ llm_service     │"
echo "  │ chroma_service      │ 50052 │ gRPC     │ chroma_service  │"
echo "  │ registry_service    │ 50053 │ gRPC     │ registry_service│"
echo "  │ sandbox_service     │ 50055 │ gRPC     │ sandbox_service │"
echo "  │ dashboard_service   │ 5001  │ HTTP     │ dashboard_service│"
echo "  │ bridge_service (MCP)│ 8100  │ HTTP/SSE │ bridge_service  │"
echo "  │ ui_service          │ 3000  │ HTTP     │ ui_service      │"
echo "  │ prometheus          │ 9090  │ HTTP     │ prometheus      │"
echo "  │ grafana             │ 3001  │ HTTP     │ grafana         │"
echo "  │ otel-collector      │ 4317  │ OTLP     │ otel-collector  │"
echo "  └─────────────────────┴───────┴──────────┴─────────────────┘"

# DNS Resolution Test
echo ""
echo "▶ DNS Resolution Test (inside orchestrator container)"
echo "─────────────────────────────────────────────────────────────"
docker exec orchestrator sh -c 'for svc in llm_service chroma_service registry_service; do getent hosts $svc 2>/dev/null && echo "  ✅ $svc resolves" || echo "  ❌ $svc does NOT resolve"; done' 2>/dev/null || echo "  ❌ orchestrator container not running"

# Summary
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Track E Summary - Actions Required"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  E1. gRPC Health:"
echo "      - Add grpc_health to all gRPC servers"
echo "      - Update health check commands in Makefile"
echo "      - Add 'make grpc-health' target"
echo ""
echo "  E2. Service Discovery Documentation:"
echo "      - Add network map table to RUNBOOK_DOCKER.md"
echo "      - Document DNS resolution for containers"
echo "      - Add troubleshooting commands"
echo ""
