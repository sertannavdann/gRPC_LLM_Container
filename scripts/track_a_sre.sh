#!/bin/bash
# Track A: SRE Tasks - Health Checks, Rate Limiting, PostgreSQL
# Skill: systems_engineer_sre.md

set -e
cd "$(dirname "$0")/.."

echo "═══════════════════════════════════════════════════════════"
echo "  Track A: Infrastructure & Reliability (SRE)"
echo "═══════════════════════════════════════════════════════════"

# A1. Health Checks
echo ""
echo "▶ A1. Health Check Status"
echo "─────────────────────────────────────────────────────────────"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Health}}" 2>/dev/null || echo "Services not running"

# Check which services need health endpoints
echo ""
echo "▶ Services needing health endpoint implementation:"
echo "─────────────────────────────────────────────────────────────"
for svc in orchestrator llm_service chroma_service dashboard_service bridge_service sandbox_service; do
    if ! grep -A5 "$svc" docker-compose.yaml 2>/dev/null | grep -q "healthcheck:"; then
        echo "  - $svc: needs healthcheck in docker-compose.yaml"
    fi
done

# A2. Rate Limiting Check
echo ""
echo "▶ A2. Rate Limiting Status"
echo "─────────────────────────────────────────────────────────────"
if [ -f "shared/utils/rate_limiter.py" ]; then
    echo "  ✅ rate_limiter.py exists"
else
    echo "  ❌ rate_limiter.py NOT FOUND - needs creation"
fi

# Check if rate limiting is integrated in providers
if grep -q "rate_limit\|RateLimiter" shared/providers/*.py 2>/dev/null; then
    echo "  ✅ Rate limiting integrated in providers"
else
    echo "  ❌ Rate limiting NOT integrated in providers"
fi

# A3. PostgreSQL Status
echo ""
echo "▶ A3. PostgreSQL Migration Status"
echo "─────────────────────────────────────────────────────────────"
if grep -q "postgres:" docker-compose.yaml 2>/dev/null; then
    echo "  ✅ PostgreSQL service defined in docker-compose.yaml"
else
    echo "  ❌ PostgreSQL service NOT defined"
fi

if [ -d "shared/database" ]; then
    echo "  ✅ shared/database/ module exists"
else
    echo "  ❌ shared/database/ module NOT FOUND"
fi

# Summary
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Track A Summary - Actions Required"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  A1. Health Checks:"
echo "      - Add /health HTTP endpoint to Python services"
echo "      - Update docker-compose.yaml with healthcheck blocks"
echo "      - Add gRPC health.v1.Health to gRPC services"
echo ""
echo "  A2. Rate Limiting:"
echo "      - Create shared/utils/rate_limiter.py"
echo "      - Integrate TokenBucketRateLimiter in ProviderRegistry"
echo "      - Add Prometheus metrics for rate limit events"
echo ""
echo "  A3. PostgreSQL:"
echo "      - Add postgres service to docker-compose.yaml"
echo "      - Create shared/database/ with connection pooling"
echo "      - Migrate Checkpointer from SQLite to PostgreSQL"
echo ""
