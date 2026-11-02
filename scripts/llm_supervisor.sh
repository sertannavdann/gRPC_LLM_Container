#!/usr/bin/env bash
# Supervise host-native LLM tiers (macOS Metal / MLX).
#
#   scripts/llm_supervisor.sh start   [tier...]   start tiers and wait until SERVING
#   scripts/llm_supervisor.sh stop    [tier...]
#   scripts/llm_supervisor.sh restart [tier...]
#   scripts/llm_supervisor.sh status  [tier...]
#   scripts/llm_supervisor.sh wait    [tier...]
#   scripts/llm_supervisor.sh logs    <tier>
#
# A tier is config/llm/<tier>.env. Default tiers come from LLM_TIERS
# (default "heavy standard"). Pid and log files live in logs/llm/.
# The root .env is never sourced: there LLM_HOST names the server the
# orchestrator dials, here it is the address this server binds.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${LLM_VENV:-$ROOT/llm_service/.venv}"
PY="$VENV/bin/python"
RUN="$ROOT/logs/llm"
READY_TIMEOUT="${LLM_READY_TIMEOUT:-300}"
mkdir -p "$RUN"

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; C=$'\033[36m'; B=$'\033[1m'; N=$'\033[0m'
else G=""; R=""; Y=""; C=""; B=""; N=""; fi

die() { printf '%s✗ %s%s\n' "$R" "$*" "$N" >&2; exit 1; }

env_file() { echo "$ROOT/config/llm/$1.env"; }

tier_port() {
  local f; f="$(env_file "$1")"
  [ -f "$f" ] || die "unknown tier '$1' (no $f)"
  sed -n 's/^LLM_PORT=//p' "$f" | tail -1
}

pid_of() {
  local pf="$RUN/$1.pid"
  [ -f "$pf" ] || return 1
  local pid; pid="$(cat "$pf")"
  kill -0 "$pid" 2>/dev/null && { echo "$pid"; return 0; }
  rm -f "$pf"; return 1
}

# Exit 0 = SERVING, 2 = NOT_SERVING (loading), 1 = unreachable.
health() {
  "$PY" - "localhost:$1" <<'PYEOF' 2>/dev/null
import sys, grpc
from grpc_health.v1 import health_pb2 as h, health_pb2_grpc as g
try:
    r = g.HealthStub(grpc.insecure_channel(sys.argv[1])).Check(h.HealthCheckRequest(service=""), timeout=2)
    sys.exit(0 if r.status == h.HealthCheckResponse.SERVING else 2)
except Exception:
    sys.exit(1)
PYEOF
}

describe() {
  "$PY" - "localhost:$1" "$ROOT" <<'PYEOF' 2>/dev/null || echo "?"
import sys, grpc
sys.path.insert(0, sys.argv[2])
from llm_service import llm_pb2, llm_pb2_grpc
m = llm_pb2_grpc.LLMServiceStub(grpc.insecure_channel(sys.argv[1])).GetActiveModel(
    llm_pb2.GetActiveModelRequest(), timeout=3)
print(f"{m.model_name} tier={m.tier} engine={m.engine or 'n/a'} device={m.device or 'n/a'} ctx={m.context_window}")
PYEOF
}

port_holder() { { lsof -nP -iTCP:"$1" -sTCP:LISTEN -Fc 2>/dev/null || true; } | sed -n "s/^c//p" | head -1; }

start_one() {
  local tier="$1" port pid holder
  port="$(tier_port "$tier")"
  if pid="$(pid_of "$tier")"; then
    printf '  %s●%s %-14s already running (pid %s, :%s)\n' "$G" "$N" "$tier" "$pid" "$port"; return 0
  fi
  holder="$(port_holder "$port")"
  if [ -n "$holder" ]; then
    case "$holder" in
      com.docker*|*docker*|vpnkit*) die "port $port is held by Docker. Run: docker stop llm_service llm_service_standard" ;;
      *) die "port $port is already in use by '$holder' (another tier on the same port?)" ;;
    esac
  fi
  [ -x "$PY" ] || die "no venv at $VENV. Run: make llm-venv"

  (
    cd "$ROOT"
    set -a
    # shellcheck disable=SC1090
    . "$(env_file "$tier")"
    set +a
    export LLM_THREADS="${LLM_THREADS:-$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null || getconf _NPROCESSORS_ONLN)}"
    export HF_HOME="${HF_HOME:-$ROOT/llm_service/models.nosync/hf}"
    export PYTHONUNBUFFERED=1
    printf '\n===== %s start %s =====\n' "$tier" "$(date '+%F %T')" >>"$RUN/$tier.log"
    nohup "$PY" -m llm_service.llm_service >>"$RUN/$tier.log" 2>&1 &
    echo $! >"$RUN/$tier.pid"
  )
  printf '  %s◐%s %-14s starting (pid %s, :%s), log logs/llm/%s.log\n' "$Y" "$N" "$tier" "$(cat "$RUN/$tier.pid")" "$port" "$tier"
}

wait_one() {
  local tier="$1" port deadline rc
  port="$(tier_port "$tier")"
  deadline=$(( $(date +%s) + READY_TIMEOUT ))
  while :; do
    if ! pid_of "$tier" >/dev/null; then
      printf '%s✗ %s exited during startup. Last log lines:%s\n' "$R" "$tier" "$N" >&2
      tail -20 "$RUN/$tier.log" >&2
      return 1
    fi
    rc=0; health "$port" || rc=$?
    if [ "$rc" -eq 0 ]; then
      printf '  %s●%s %-14s SERVING  %s\n' "$G" "$N" "$tier" "$(describe "$port")"; return 0
    fi
    [ "$(date +%s)" -lt "$deadline" ] || { printf '%s✗ %s not SERVING after %ss%s\n' "$R" "$tier" "$READY_TIMEOUT" "$N" >&2; return 1; }
    sleep 2
  done
}

stop_one() {
  local tier="$1" pid i
  if ! pid="$(pid_of "$tier")"; then printf '  ○ %-14s not running\n' "$tier"; return 0; fi
  kill -TERM "$pid" 2>/dev/null || true
  for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
  kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
  rm -f "$RUN/$tier.pid"
  printf '  %s○%s %-14s stopped (pid %s)\n' "$C" "$N" "$tier" "$pid"
}

status_one() {
  local tier="$1" port pid rc
  port="$(tier_port "$tier")"
  if pid="$(pid_of "$tier")"; then
    rc=0; health "$port" || rc=$?
    case "$rc" in
      0) printf '  %s●%s %-14s %shealthy%s  :%s pid %-6s %s\n' "$G" "$N" "$tier" "$G" "$N" "$port" "$pid" "$(describe "$port")" ;;
      2) printf '  %s◐%s %-14s %sloading%s  :%s pid %s\n' "$Y" "$N" "$tier" "$Y" "$N" "$port" "$pid" ;;
      *) printf '  %s○%s %-14s %sunreachable%s :%s pid %s\n' "$R" "$N" "$tier" "$R" "$N" "$port" "$pid" ;;
    esac
  else
    printf '  ○ %-14s stopped  :%s\n' "$tier" "$port"
  fi
}

cmd="${1:-status}"; shift || true
if [ "$#" -gt 0 ]; then TIERS=("$@"); else read -r -a TIERS <<<"${LLM_TIERS:-heavy standard}"; fi

# status with no explicit tiers also shows any other tier that has a pid file.
if [ "$cmd" = "status" ] && [ "$#" -eq 0 ]; then
  for pf in "$RUN"/*.pid; do
    [ -e "$pf" ] || continue
    t="$(basename "$pf" .pid)"
    case " ${TIERS[*]} " in *" $t "*) ;; *) TIERS+=("$t") ;; esac
  done
fi

case "$cmd" in
  start)
    for t in "${TIERS[@]}"; do start_one "$t"; done
    for t in "${TIERS[@]}"; do wait_one "$t"; done ;;
  wait)    for t in "${TIERS[@]}"; do wait_one "$t"; done ;;
  stop)    for t in "${TIERS[@]}"; do stop_one "$t"; done ;;
  restart) for t in "${TIERS[@]}"; do stop_one "$t"; done
           for t in "${TIERS[@]}"; do start_one "$t"; done
           for t in "${TIERS[@]}"; do wait_one "$t"; done ;;
  status)  for t in "${TIERS[@]}"; do status_one "$t"; done ;;
  logs)    exec tail -n 50 -f "$RUN/${TIERS[0]}.log" ;;
  *) die "usage: $0 {start|stop|restart|status|wait|logs} [tier...]" ;;
esac
