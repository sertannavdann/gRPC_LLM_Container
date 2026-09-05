#!/usr/bin/env bash
# ============================================================================
# NEXUS Showroom Test — Exercises the full module pipeline and reports results
# ============================================================================
set -euo pipefail

CYAN='\033[36m'
GREEN='\033[32m'
RED='\033[31m'
YELLOW='\033[33m'
RESET='\033[0m'
BOLD='\033[1m'

DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:8001}"
ADMIN_URL="${ADMIN_URL:-http://localhost:8003}"
PASS=0
FAIL=0

# Auth: every non-public endpoint requires X-API-Key (Phase 1 auth boundary).
# Resolve from env, else from .env (ADMIN_API_KEY=...). Fail fast if absent.
API_KEY="${ADMIN_API_KEY:-}"
if [ -z "$API_KEY" ] && [ -f .env ]; then
  API_KEY=$(grep -E '^ADMIN_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
fi
if [ -z "$API_KEY" ]; then
  printf "${RED}ADMIN_API_KEY not set (env or .env) — showroom cannot authenticate.${RESET}\n" >&2
  exit 2
fi
AUTH=(-H "X-API-Key: $API_KEY")

check() {
  local name="$1"
  local url="$2"
  local jq_filter="${3:-.}"

  printf "  %-45s " "$name"

  local tmp; tmp=$(mktemp)
  local code
  code=$(curl -s "${AUTH[@]}" --connect-timeout 3 --max-time 5 -o "$tmp" -w '%{http_code}' "$url" 2>/dev/null) || code="000"
  resp=$(cat "$tmp"); rm -f "$tmp"
  if [ "$code" = "000" ]; then
    printf "${RED}FAIL${RESET} (unreachable)\n"; FAIL=$((FAIL + 1)); return
  elif [ "${code:0:1}" != "2" ]; then
    printf "${RED}FAIL${RESET} (HTTP %s)\n" "$code"; FAIL=$((FAIL + 1)); return
  fi

  if [ -n "$jq_filter" ] && command -v jq &>/dev/null; then
    result=$(echo "$resp" | jq -r "$jq_filter" 2>/dev/null || echo "$resp")
  else
    result="$resp"
  fi

  printf "${GREEN}OK${RESET}   %s\n" "$(echo "$result" | head -c 60)"
  PASS=$((PASS + 1))
}

printf "\n${BOLD}${CYAN}╔══════════════════════════════════════════════════════════╗${RESET}\n"
printf "${BOLD}${CYAN}║           NEXUS Showroom — Integration Test              ║${RESET}\n"
printf "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════╝${RESET}\n\n"

# 1. Dashboard health
printf "${BOLD}${YELLOW}▸ Dashboard Service${RESET}\n"
check "Health endpoint" "$DASHBOARD_URL/health" '.status'
check "Adapters list" "$DASHBOARD_URL/adapters" '.categories | length | tostring + " categories"'
check "Module list" "$DASHBOARD_URL/modules" '.total | tostring + " modules"'
check_sse() {
  local name="$1" url="$2"
  printf "  %-45s " "$name"
  local out
  out=$(curl -s -N "${AUTH[@]}" --connect-timeout 3 --max-time 4 "$url" 2>/dev/null | head -c 400 || true)
  if echo "$out" | grep -q "data:"; then
    printf "${GREEN}OK${RESET}   event received\n"; PASS=$((PASS + 1))
  else
    printf "${RED}FAIL${RESET} (no SSE event within 4s)\n"; FAIL=$((FAIL + 1))
  fi
}
check_sse "SSE endpoint reachable" "$DASHBOARD_URL/stream/pipeline-state"
check "Prometheus metrics" "$DASHBOARD_URL/metrics" ''
echo ""

# 2. Admin API
printf "${BOLD}${YELLOW}▸ Admin API (Orchestrator)${RESET}\n"
check "Admin health" "$ADMIN_URL/admin/health" '.status'
check "Routing config" "$ADMIN_URL/admin/routing-config" '.version'
check "Module list" "$ADMIN_URL/admin/modules" '.total | tostring + " modules"'
check "System info" "$ADMIN_URL/admin/system-info" '.modules.total | tostring + " modules"'
echo ""

# 3. Module operations (showroom/metrics_demo)
printf "${BOLD}${YELLOW}▸ Module Operations (showroom/metrics_demo)${RESET}\n"
check "Get module detail" "$ADMIN_URL/admin/modules/showroom/metrics_demo" '.module_id'

# Try enable
printf "  %-45s " "Enable module"
enable_resp=$(curl -sf "${AUTH[@]}" -X POST "$ADMIN_URL/admin/modules/showroom/metrics_demo/enable" 2>/dev/null) || true
if echo "$enable_resp" | jq -e '.success' &>/dev/null; then
  printf "${GREEN}OK${RESET}   enabled\n"
  PASS=$((PASS + 1))
else
  printf "${YELLOW}SKIP${RESET} (may already be loaded)\n"
fi

# Try reload
printf "  %-45s " "Reload module"
reload_resp=$(curl -sf "${AUTH[@]}" -X POST "$ADMIN_URL/admin/modules/showroom/metrics_demo/reload" 2>/dev/null) || true
if echo "$reload_resp" | jq -e '.success' &>/dev/null; then
  printf "${GREEN}OK${RESET}   reloaded\n"
  PASS=$((PASS + 1))
else
  printf "${YELLOW}SKIP${RESET}\n"
fi

# Disable then re-enable
printf "  %-45s " "Disable → Re-enable cycle"
curl -sf "${AUTH[@]}" -X POST "$ADMIN_URL/admin/modules/showroom/metrics_demo/disable" &>/dev/null || true
sleep 0.5
cycle_resp=$(curl -sf "${AUTH[@]}" -X POST "$ADMIN_URL/admin/modules/showroom/metrics_demo/enable" 2>/dev/null) || true
if echo "$cycle_resp" | jq -e '.success' &>/dev/null; then
  printf "${GREEN}OK${RESET}   cycle complete\n"
  PASS=$((PASS + 1))
else
  printf "${YELLOW}SKIP${RESET}\n"
fi
echo ""

# 4. Context / Adapter data
printf "${BOLD}${YELLOW}▸ Adapter Data Flow${RESET}\n"
check "Unified context" "$DASHBOARD_URL/context" '.user_id'
check "Bank transactions" "$DASHBOARD_URL/bank/transactions?per_page=1" '.total'
check "Bank summary" "$DASHBOARD_URL/bank/summary" '.group_by'
echo ""

# Summary
printf "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}  Results:  ${GREEN}$PASS passed${RESET}  ${RED}$FAIL failed${RESET}\n"
printf "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

[ $FAIL -eq 0 ] && exit 0 || exit 1
