# Docker Runbook (Rebuild + Restart Everything)

This is a practical reference for getting **all services rebuilt and running in a healthy “active” state**.

## What “active state” means here
- Containers are **Up**: `make ps` or `docker compose ps`
- Health checks are **healthy** (where defined): `make status` / `make health-all`
- Orchestrator answers requests: `grpcurl -plaintext localhost:50054 list`
- UI responds: open `http://localhost:5001`

---

## The 3 most common flows

### 1) Fresh rebuild of everything (recommended when code changes aren’t showing up)
Uses **no cache** + **force recreate**.

- `make rebuild-all`
- `make status`
- `make logs-tail`

Docker Compose equivalent:
- `docker compose build --no-cache`
- `docker compose up -d --force-recreate`

### 2) Fast restart of everything (recommended when code didn’t change)
Uses existing images (fast).

- `make restart-all`
- `make status`

Docker Compose equivalent:
- `docker compose restart`

### 3) Build+start everything (first-time bring-up)
Builds (with cache) then starts.

- `make start`

---

## Selective rebuild/restart (faster iteration)

### Orchestrator only
- No-cache rebuild + recreate:
  - `make rebuild-orchestrator`
- Quick rebuild using cache:
  - `make quick-orchestrator`
- Quick restart:
  - `make restart-orchestrator`
- Tail logs:
  - `make logs-orch`

### Any single service (pattern targets)
- Build service: `make build-<svc>`
- Restart service: `make restart-<svc>`
- Logs: `make logs-<svc>`
- Shell: `make shell-<svc>`

Services: `orchestrator`, `llm_service`, `chroma_service`, `sandbox_service`, `registry_service`, `ui_service`

---

## Quick health verification

### Compose-level
- `make status` (prints container status + health + provider status)
- `make health-all`
- `make stats`

### gRPC-level (orchestrator)
- List services:
  - `grpcurl -plaintext localhost:50054 list`
- Send a quick query:
  - `grpcurl -plaintext -d '{"user_query":"ping"}' localhost:50054 agent.AgentService/QueryAgent`

---

## When logs “fail” with exit code 130
That usually means you hit **Ctrl+C** to stop `make logs` (which is expected).

Use these instead:
- `make logs-tail` (tails the last lines and continues following)
- `make logs-orch` (orchestrator-focused)

---

## “Code changes not reflected” checklist
1) Verify you’re hitting the expected container:
- `make ps`

2) Verify code inside container (orchestrator example):
- `make verify-code`

3) If still stale, force rebuild:
- `make rebuild-orchestrator` (orchestrator only)
- `make rebuild-all` (everything)

---

## Clean slate (only when you truly want to reset)
This stops containers and removes Compose-managed volumes (bind-mount data on disk is not deleted).

- `make clean-docker`
- `make rebuild-all`

If you also want to remove local images built by this project:
- `make clean-all`

---

## Tips
- Prefer `make rebuild-orchestrator` when iterating on tool/orchestrator logic; it’s the most common “Docker cache bit me” fix.
- Prefer `make status` after any restart/rebuild. It’s the fastest signal.
---

## Full rebuild + restart containers via Makefile

When you need a complete "nuclear option" rebuild with verification:

```bash
make rebuild-all && make status && make health
```

Breakdown:
1. `make rebuild-all` - Rebuilds **all** services without cache + force recreates containers
2. `make status` - Shows container status, ports, and current provider config
3. `make health` - Checks gRPC health endpoints for all services

Alternatively, use the all-in-one:
```bash
make start
```
This does: `build` (with cache) → `up` → `status` in one shot.

**When to use which:**
- **First time setup**: `make start`
- **Code changes not showing**: `make rebuild-all`
- **Quick iteration (no code change)**: `make restart-all`

---

## UI Development Options

### Option 1: Local npm dev server (hot reload, port 3000)
**Recommended for UI-only development.**

```bash
# Start backend services only
make dev-backend

# In another terminal, start UI dev server
make dev-ui-local

# Or run both at once
make dev
```

This runs `npm run dev` inside `ui_service/` and serves on **http://localhost:3000** with Next.js hot reload.

**Requirements:**
- Node.js installed locally
- `npm install` completed in `ui_service/`

### Option 2: Dockerized UI (port 5001)
**Use when you need the full production-like stack.**

```bash
# Start everything including UI in Docker
make start

# Or just the UI container
make dev-ui-docker
```

UI serves on **http://localhost:5001** (mapped from container port 5000).

**Trade-offs:**
| Mode | Port | Hot Reload | Setup |
|------|------|------------|-------|
| Local npm | 3000 | ✅ Yes | Requires Node.js |
| Docker | 5001 | ❌ No (rebuild required) | Docker only |

**Tip:** Use local npm during active UI development, switch to Docker for integration testing.

## Full rebuild restart containers via Makefile
