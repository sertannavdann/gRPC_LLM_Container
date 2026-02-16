#!/usr/bin/env bash
set -uo pipefail
# ============================================================================
# NEXUS Release Verification Pipeline
# ============================================================================
# Runs all test tiers in sequence, produces structured pass/fail report.
#
# Usage:
#   bash scripts/verify.sh              # bail on first failure
#   bash scripts/verify.sh --no-bail    # run all steps even if one fails
#   bash scripts/verify.sh --skip-showroom  # skip showroom + latency (CI)
# ============================================================================

CYAN='\033[36m'
GREEN='\033[32m'
RED='\033[31m'
YELLOW='\033[33m'
BOLD='\033[1m'
RESET='\033[0m'

BAIL=true
SKIP_SHOWROOM=false

for arg in "$@"; do
  case "$arg" in
    --no-bail) BAIL=false ;;
    --skip-showroom) SKIP_SHOWROOM=true ;;
  esac
done

# Track results
declare -a STEP_NAMES
declare -a STEP_STATUSES
declare -a STEP_DURATIONS
TOTAL=0
PASSED=0
FAILED=0
PIPELINE_START=$(date +%s)

run_step() {
  local name="$1"
  shift
  local cmd="$*"

  TOTAL=$((TOTAL + 1))
  printf "\n${BOLD}${CYAN}━━━ [%d] %s ━━━${RESET}\n" "$TOTAL" "$name"

  local step_start
  step_start=$(date +%s)

  eval "$cmd" 2>&1
  local rc=$?

  local step_end
  step_end=$(date +%s)
  local duration=$((step_end - step_start))

  STEP_NAMES+=("$name")
  STEP_DURATIONS+=("${duration}s")

  if [ $rc -eq 0 ]; then
    STEP_STATUSES+=("PASS")
    PASSED=$((PASSED + 1))
    printf "${GREEN}✓ %s PASSED${RESET} (%ds)\n" "$name" "$duration"
  else
    STEP_STATUSES+=("FAIL")
    FAILED=$((FAILED + 1))
    printf "${RED}✗ %s FAILED${RESET} (exit %d, %ds)\n" "$name" "$rc" "$duration"
    if $BAIL; then
      printf "\n${RED}${BOLD}Bailing on first failure. Use --no-bail to continue.${RESET}\n"
      print_summary
      exit 1
    fi
  fi
}

skip_step() {
  local name="$1"
  local reason="$2"
  TOTAL=$((TOTAL + 1))
  STEP_NAMES+=("$name")
  STEP_STATUSES+=("SKIP")
  STEP_DURATIONS+=("0s")
  printf "\n${YELLOW}― [%d] %s SKIPPED (%s)${RESET}\n" "$TOTAL" "$name" "$reason"
}

print_summary() {
  local pipeline_end
  pipeline_end=$(date +%s)
  local total_duration=$((pipeline_end - PIPELINE_START))

  printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
  printf "${BOLD} NEXUS Verification Report${RESET}\n"
  printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

  printf "%-40s %-8s %s\n" "Step" "Status" "Duration"
  printf "%-40s %-8s %s\n" "----" "------" "--------"

  for i in "${!STEP_NAMES[@]}"; do
    local status="${STEP_STATUSES[$i]}"
    local color="$RESET"
    case "$status" in
      PASS) color="$GREEN" ;;
      FAIL) color="$RED" ;;
      SKIP) color="$YELLOW" ;;
    esac
    printf "%-40s ${color}%-8s${RESET} %s\n" "${STEP_NAMES[$i]}" "$status" "${STEP_DURATIONS[$i]}"
  done

  printf "\n${BOLD}Total: %d/%d passed" "$PASSED" "$((PASSED + FAILED))"
  if [ "$FAILED" -gt 0 ]; then
    printf " ${RED}(%d failed)${RESET}" "$FAILED"
  fi
  printf " in %ds${RESET}\n" "$total_duration"

  if [ -f "data/verify_snapshot.json" ]; then
    printf "\n${CYAN}Latency snapshot: data/verify_snapshot.json${RESET}\n"
  fi
}

# ============================================================================
# Test Tiers
# ============================================================================

printf "${BOLD}${CYAN}NEXUS Release Verification Pipeline${RESET}\n"
printf "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')\n"

# 1. Unit tests
if [ -d "tests/unit" ]; then
  run_step "Unit Tests" "python -m pytest tests/unit/ -q --tb=line"
else
  skip_step "Unit Tests" "tests/unit/ not found"
fi

# 2. Contract tests
if [ -d "tests/contract" ]; then
  run_step "Contract Tests" "python -m pytest tests/contract/ -q --tb=line"
else
  skip_step "Contract Tests" "tests/contract/ not found"
fi

# 3. Integration tests
if [ -d "tests/integration" ]; then
  run_step "Integration Tests" "python -m pytest tests/integration/ -q --tb=line"
else
  skip_step "Integration Tests" "tests/integration/ not found"
fi

# 4. Feature tests
if [ -d "tests/feature" ]; then
  run_step "Feature Tests" "python -m pytest tests/feature/ -q --tb=line"
else
  skip_step "Feature Tests" "tests/feature/ not found"
fi

# 5. Scenario tests
if [ -d "tests/scenarios" ]; then
  run_step "Scenario Tests" "python -m pytest tests/scenarios/ -q --tb=line"
else
  skip_step "Scenario Tests" "tests/scenarios/ not found"
fi

# 6. Showroom (requires running services)
if $SKIP_SHOWROOM; then
  skip_step "Showroom" "--skip-showroom flag"
  skip_step "Latency Snapshot" "--skip-showroom flag"
else
  # Check if services are running
  if curl -sf http://localhost:8003/admin/health >/dev/null 2>&1; then
    run_step "Showroom" "bash scripts/showroom_test.sh"
    run_step "Latency Snapshot" "python -m shared.billing.latency_snapshot"
  else
    skip_step "Showroom" "services not running"
    skip_step "Latency Snapshot" "services not running"
  fi
fi

# ============================================================================
# Summary
# ============================================================================

print_summary

if [ "$FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
