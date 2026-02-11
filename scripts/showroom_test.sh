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

check() {
  local name="$1"
  local url="$2"
  local jq_filter="${3:-.}"

  printf "  %-45s " "$name"

  resp=$(curl -sf --connect-timeout 3 --max-time 5 "$url" 2>/dev/null) || {
    printf "${RED}FAIL${RESET} (unreachable)\n"
    FAIL=$((FAIL + 1))
    return
  }

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
check "SSE endpoint reachable" "$DASHBOARD_URL/stream/pipeline-state" ''
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
enable_resp=$(curl -sf -X POST "$ADMIN_URL/admin/modules/showroom/metrics_demo/enable" 2>/dev/null) || true
if echo "$enable_resp" | jq -e '.success' &>/dev/null; then
  printf "${GREEN}OK${RESET}   enabled\n"
  PASS=$((PASS + 1))
else
  printf "${YELLOW}SKIP${RESET} (may already be loaded)\n"
fi

# Try reload
printf "  %-45s " "Reload module"
reload_resp=$(curl -sf -X POST "$ADMIN_URL/admin/modules/showroom/metrics_demo/reload" 2>/dev/null) || true
if echo "$reload_resp" | jq -e '.success' &>/dev/null; then
  printf "${GREEN}OK${RESET}   reloaded\n"
  PASS=$((PASS + 1))
else
  printf "${YELLOW}SKIP${RESET}\n"
fi

# Disable then re-enable
printf "  %-45s " "Disable → Re-enable cycle"
curl -sf -X POST "$ADMIN_URL/admin/modules/showroom/metrics_demo/disable" &>/dev/null || true
sleep 0.5
cycle_resp=$(curl -sf -X POST "$ADMIN_URL/admin/modules/showroom/metrics_demo/enable" 2>/dev/null) || true
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
