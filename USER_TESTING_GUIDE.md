# NEXUS Agent Platform — Manual Testing Guide

> **Last Updated**: February 15, 2026
> **Version**: 4.0 (NEXUS branch)
> **Tester**: _________________________
> **Date Tested**: _________________________

---

## How to Use This Guide

Work through each section top-to-bottom. For each test, record whether it works, rate quality 1-5, and note any issues. Mark tests as:
- **PASS** — works as expected
- **FAIL** — broken or incorrect behavior
- **SKIP** — requires config/keys you don't have
- **PARTIAL** — works but with issues

---

## 0. Prerequisites & Setup

### Required Software
- Docker Desktop 4.x (running)
- Web browser (Chrome recommended)
- Terminal access
- Python 3.12+ (for running pytest locally)

### Environment Setup
```bash
cd /Users/sertanavdan/Documents/Software/AI/gRPC_llm

# Copy env template if first time
cp .env.example .env

# Optional API keys (for real adapter integrations):
# OPENWEATHER_API_KEY=...
# CLASH_ROYALE_API_KEY=...
# CLASH_ROYALE_PLAYER_TAG=%23YOUR_TAG
# SERPER_API_KEY=...
# GOOGLE_CALENDAR_CLIENT_ID=...
# GOOGLE_CALENDAR_CLIENT_SECRET=...
# GOOGLE_CALENDAR_ACCESS_TOKEN=...
# GOOGLE_CALENDAR_REFRESH_TOKEN=...

# Module encryption (required for credential store):
# MODULE_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

### Start All Services
```bash
make build && make up
# Wait ~60s for all containers to initialize
make status
```

### Quick Health Verification
```bash
curl -s http://localhost:8001/health | jq    # Dashboard
curl -s http://localhost:8003/admin/health | jq  # Admin API
curl -s http://localhost:8100/health | jq    # Bridge
```

| Check | Status |
|-------|--------|
| `make status` shows all containers green? | PASS / FAIL |
| Dashboard health returns `{"status": "healthy"}`? | PASS / FAIL |
| Admin API health returns OK? | PASS / FAIL |
| Bridge health returns OK? | PASS / FAIL |
| Grafana loads at http://localhost:3001? | PASS / FAIL |

### Service Port Reference

| Service | Port | URL |
|---------|------|-----|
| UI Service (Next.js) | 5001 | http://localhost:5001 |
| Dashboard Service (FastAPI) | 8001 | http://localhost:8001 |
| Admin API | 8003 | http://localhost:8003 |
| Bridge Service (MCP) | 8100 | http://localhost:8100 |
| Grafana | 3001 | http://localhost:3001 |
| Prometheus | 9090 | http://localhost:9090 |
| Orchestrator (gRPC) | 50054 | — |
| LLM Service (gRPC) | 50051 | — |
| Sandbox Service (gRPC) | 50057 | — |
| Chroma Service (gRPC) | 50052 | — |
| OTel Collector | 4317/4318 | — |
| Tempo | 3200 | — |
| cAdvisor | 8080 | http://localhost:8080 |

---

## 1. UI Navigation & Landing Page

**URL**: http://localhost:5001

### 1.1 Landing Page

| Test | Result | Notes |
|------|--------|-------|
| Page loads without errors? | | |
| Hero section shows "gRPC LLM Agent" title? | | |
| 6 page cards visible (Chat, Dashboard, Finance, Integrations, Monitoring, Settings)? | | |
| Each card has icon, badge, and description? | | |
| Click each card navigates to correct page? | | |

### 1.2 Navbar

| Test | Result | Notes |
|------|--------|-------|
| Navbar visible at top on all pages? | | |
| 8 nav items: Home, Chat, Dashboard, Finance, Integrations, Pipeline, Monitoring, Settings? | | |
| Active page highlighted in navbar? | | |
| Green "Connected" status indicator in top-right? | | |
| Brand logo links back to home? | | |
| Nav items collapse on mobile (icons only)? | | |

---

## 2. Chat Interface

**URL**: http://localhost:5001/chat

### 2.1 Basic Conversation

| Test | Input | Expected | Result | Notes |
|------|-------|----------|--------|-------|
| Greeting | "Hello, how are you?" | Friendly response | | |
| Memory | "My name is Alex" then "What is my name?" | Remembers "Alex" | | |
| Long response | "Explain quantum computing in detail" | Streams multi-paragraph response | | |

### 2.2 Tool Calling — Math

| Test | Input | Expected | Result | Notes |
|------|-------|----------|--------|-------|
| Simple | "What is 2 + 2?" | 4 | | |
| Complex | "Calculate 15 * 23" | 345 | | |
| Expression | "What is (5 + 3) * 2 - 7 / 2?" | 12.5 | | |
| Word problem | "If I have 120 apples and give away 30%, how many left?" | 84 | | |

### 2.3 Tool Calling — Code Execution (Sandbox)

| Test | Input | Expected | Result | Notes |
|------|-------|----------|--------|-------|
| Print | "Execute: print('Hello World')" | Shows "Hello World" | | |
| Computation | "Run: x = [1,2,3,4,5]; print(sum(x))" | Shows "15" | | |
| Loop | "Execute: for i in range(5): print(i*2)" | 0 2 4 6 8 | | |
| Error handling | "Run: int('not a number')" | Shows ValueError gracefully | | |
| Timeout | "Execute: import time; time.sleep(60)" | Timeout after ~30s | | |

### 2.4 Tool Calling — Knowledge Search (ChromaDB)

| Test | Input | Expected | Result | Notes |
|------|-------|----------|--------|-------|
| Search | "Search knowledge base for Python" | Returns results or graceful empty | | |
| No results | "Search for xyzzy123nonsense" | Handles gracefully | | |

### 2.5 Tool Calling — Web Search (requires SERPER_API_KEY)

| Test | Input | Expected | Result | Notes |
|------|-------|----------|--------|-------|
| Web search | "Search the web for Python 3.12 features" | Returns web results | | |

### 2.6 Context & Weather/Gaming (requires API keys)

| Test | Input | Expected | Result | Notes |
|------|-------|----------|--------|-------|
| Weather | "What's the weather right now?" | Temperature + conditions | | |
| Gaming | "How are my Clash Royale stats?" | Trophies + win rate | | |
| Full status | "Give me a full status update" | Aggregated context | | |

### 2.7 Security

| Test | Input | Expected | Result | Notes |
|------|-------|----------|--------|-------|
| XSS | "Test `<script>alert('xss')</script>`" | Sanitized/escaped output | | |
| Empty input | (send empty message) | Graceful error | | |
| Very long input | (10,000+ chars) | Handles or limits gracefully | | |

### Chat Overall

| Criteria | Rating (1-5) | Notes |
|----------|--------------|-------|
| Response quality | | |
| Response speed | | |
| Tool selection accuracy | | |
| Error handling | | |
| UI responsiveness | | |

---

## 3. Dashboard (Unified Widgets)

**URL**: http://localhost:5001/dashboard

### 3.1 Page Load

| Test | Result | Notes |
|------|--------|-------|
| Dashboard page loads? | | |
| Widget grid renders (finance, calendar, health, weather, gaming, navigation)? | | |
| Layout adapts across breakpoints (1/2/3/4 columns)? | | |

### 3.2 Finance Widget

| Test | Result | Notes |
|------|--------|-------|
| Shows Income, Expenses, Net summary cards? | | |
| Shows recent transactions? | | |
| "Full Dashboard" link opens port 8001? | | |
| Maximize expands to full view? | | |
| Filter toggle (funnel icon) shows filter bar in expanded mode? | | |
| Category dropdown filters transactions? | | |
| Date range pickers work? | | |
| Search input filters results? | | |
| "Clear all" resets filters? | | |
| Minimize returns to grid view? | | |

### 3.3 Weather Widget (requires OPENWEATHER_API_KEY)

| Test | Result | Notes |
|------|--------|-------|
| Widget visible? | | |
| Shows current temperature? | | |
| Shows condition (clear/clouds/rain)? | | |
| Shows humidity, wind, visibility? | | |
| Forecast section displays? | | |

### 3.4 Gaming Widget (requires CLASH_ROYALE keys)

| Test | Result | Notes |
|------|--------|-------|
| Widget visible? | | |
| Shows player name and trophies? | | |
| Shows win/loss/win rate? | | |
| Recent battles listed? | | |
| Trophy changes color-coded (+green/-red)? | | |

### 3.5 Other Widgets

| Widget | Loads? | Shows data? | Notes |
|--------|--------|-------------|-------|
| Calendar | | | |
| Health | | | |
| Navigation | | | |

---

## 4. Finance Dashboard (Standalone)

**URL**: http://localhost:8001 (also embedded at http://localhost:5001/finance)

> Requires CSV files in `dashboard_service/Bank/` (cibc.csv, cibc_.csv, chq.csv)

### 4.1 Page Load

| Test | Result | Notes |
|------|--------|-------|
| Dashboard loads with dark theme? | | |
| All 4 charts render (category donut, monthly trend, top companies, account split)? | | |
| Summary cards show totals (income, expenses, net, transaction count)? | | |
| Transaction table populates? | | |
| Load time acceptable (< 3s)? | | |

### 4.2 Filtering

| Test | Result | Notes |
|------|--------|-------|
| Select category → all charts + table + cards update? | | |
| Set date range → monthly chart updates? | | |
| Type search term → top companies chart updates? | | |
| Select account filter → data scoped? | | |
| Reset → all charts return to full data? | | |

### 4.3 Transaction Table

| Test | Result | Notes |
|------|--------|-------|
| Table displays data with columns? | | |
| Pagination works? | | |
| Sorting by column headers works? | | |

### 4.4 API Endpoints

```bash
curl -s "http://localhost:8001/bank/transactions?limit=5" | jq '.total'
curl -s "http://localhost:8001/bank/summary?group_by=category" | jq
curl -s "http://localhost:8001/bank/categories" | jq '.[0]'
curl -s "http://localhost:8001/bank/search?q=amazon" | jq '.total'
```

| Endpoint | Returns data? | Notes |
|----------|--------------|-------|
| `/bank/transactions` | | |
| `/bank/summary?group_by=category` | | |
| `/bank/categories` | | |
| `/bank/search?q=amazon` | | |

---

## 5. Integrations Page

**URL**: http://localhost:5001/integrations

### 5.1 Page Structure

| Test | Result | Notes |
|------|--------|-------|
| Page loads? | | |
| "External Services" section visible? | | |
| "Built-in Sources" section visible? | | |
| Active count badge correct? | | |

### 5.2 Adapter Connection (Hot-Reload)

| Test | Result | Notes |
|------|--------|-------|
| Expand OpenWeather card → shows API Key + City fields? | | |
| Enter API key → click "Connect" → success message? | | |
| Message says "Dashboard will refresh automatically"? | | |
| No container restart needed? | | |
| Dashboard weather widget populates within 60s? | | |

### 5.3 Disconnect

| Test | Result | Notes |
|------|--------|-------|
| Click "Disconnect" on connected adapter | | |
| Status changes to "Not connected"? | | |
| Dashboard widget reverts to empty/mock? | | |

### 5.4 Built-in Sources

| Test | Result | Notes |
|------|--------|-------|
| CIBC shows as always active? | | |
| Mock adapters show as active? | | |
| No connect/disconnect buttons for built-in? | | |

### 5.5 Hot-Reload API Direct Test

```bash
# Direct hot-reload test
curl -X POST "http://localhost:8001/admin/credentials?user_id=default" \
  -H "Content-Type: application/json" \
  -d '{"category":"weather","platform":"openweather","credentials":{"api_key":"YOUR_KEY"},"settings":{"city":"Toronto,CA"}}'

# Verify
curl -s http://localhost:8001/context/weather | jq
```

| Test | Result | Notes |
|------|--------|-------|
| POST returns `{"success": true}`? | | |
| `/context/weather` returns data? | | |

---

## 6. Settings Page

**URL**: http://localhost:5001/settings

### 6.1 Provider Management

| Test | Result | Notes |
|------|--------|-------|
| Page loads? | | |
| Provider selection dropdown visible? | | |
| Current provider highlighted? | | |
| API key fields visible (Perplexity, OpenAI, Anthropic, Serper)? | | |
| Keys masked with show/hide toggle? | | |

### 6.2 Provider Switching

| Test | Result | Notes |
|------|--------|-------|
| Select different provider → click Save | | |
| Orchestrator restart triggered? | | |
| New provider active in next chat? | | |

### 6.3 LIDM Delegation Toggle

| Test | Result | Notes |
|------|--------|-------|
| "Multi-Model Delegation (LIDM)" section visible? | | |
| Toggle switch present? | | |
| Enable → Docker profile notice appears? | | |
| Heavy/Standard tier model dropdowns visible? | | |
| Selections persist after page reload? | | |

---

## 7. LIDM Multi-Model Routing

> **Prerequisites**: Enable LIDM in Settings, then: `docker compose --profile lidm up -d`

### 7.1 Tier Routing

| Test | Input | Expected Tier | Log confirms? | Notes |
|------|-------|---------------|---------------|-------|
| Simple query | "Hello, what time is it?" | Standard | | |
| Complex query | "Analyze microservice vs monolith architectures" | Heavy | | |
| Multi-tool | "Search web for Python features and run a code example" | Heavy | | |

### 7.2 Fallback

| Test | Result | Notes |
|------|--------|-------|
| Stop standard tier: `docker stop grpc_llm-llm_service_standard-1` | | |
| Send query → falls back to heavy tier? | | |
| No DEADLINE_EXCEEDED error? | | |
| Restart: `docker compose --profile lidm up -d` | | |

### 7.3 Disabled Mode

| Test | Result | Notes |
|------|--------|-------|
| Disable LIDM in Settings | | |
| Standard-tier container NOT running (verify `docker ps`) | | |
| Queries route to single LLM instance? | | |
| No errors or timeouts? | | |

---

## 8. Pipeline UI (React Flow)

**URL**: http://localhost:5001/pipeline

### 8.1 Visualization

| Test | Result | Notes |
|------|--------|-------|
| Pipeline page loads? | | |
| React Flow canvas renders? | | |
| 4 stages visible (Intent Detection, LIDM Routing, Tool Execution, Synthesis)? | | |
| Animated orange edges between stages? | | |
| Navbar shows "Pipeline" with Zap icon? | | |

### 8.2 Live SSE

| Test | Result | Notes |
|------|--------|-------|
| "Live" indicator (green Wifi icon) visible? | | |
| Service nodes appear with health status? | | |
| Health color-coded (green/red/grey)? | | |
| Latency displayed on service nodes? | | |
| Updates every ~2 seconds? | | |

### 8.3 Module Nodes

| Test | Result | Notes |
|------|--------|-------|
| Module nodes appear below pipeline? | | |
| Category badges shown? | | |
| Enable/disable toggle works? | | |
| Module state updates after toggle? | | |

### 8.4 Controls

| Test | Result | Notes |
|------|--------|-------|
| MiniMap visible in corner? | | |
| Zoom controls work? | | |
| Pan/drag canvas works? | | |
| Refresh button fetches latest modules? | | |

---

## 9. NEXUS Module System

### 9.1 Module Discovery

```bash
curl -s http://localhost:8001/modules | jq
```

| Test | Result | Notes |
|------|--------|-------|
| Returns module list with `total` count? | | |
| `test/hello` module present? | | |
| `showroom/metrics_demo` module present? | | |

### 9.2 Module Lifecycle (via Agent Chat)

| Test | Input | Result | Notes |
|------|-------|--------|-------|
| Build intent | "Build me a hello world module" | Module builder triggered? | |
| Validation | (automatic after build) | 3-stage validation runs? | |
| Install | (automatic after validation) | Module hot-loaded? | |

---

## 10. Admin API

**URL**: http://localhost:8003

### 10.1 Health & System Info

```bash
curl -s http://localhost:8003/admin/health | jq
curl -s http://localhost:8003/admin/system-info | jq
curl -s http://localhost:8003/admin/providers | jq
```

| Endpoint | Returns data? | Notes |
|----------|--------------|-------|
| `/admin/health` | | |
| `/admin/system-info` (routing categories, tiers, module counts) | | |
| `/admin/providers` (provider/model lists) | | |

### 10.2 Routing Config

```bash
curl -s http://localhost:8003/admin/routing-config | jq '.categories | keys'
```

| Test | Result | Notes |
|------|--------|-------|
| GET returns config with 13 categories? | | |
| Categories include: greeting, math, coding, weather, finance, etc.? | | |
| Tier configuration (standard, heavy) present? | | |

### 10.3 Module CRUD

```bash
# List all modules
curl -s http://localhost:8003/admin/modules | jq

# Get specific module
curl -s http://localhost:8003/admin/modules/test/hello | jq

# Enable/Disable/Reload cycle
curl -s -X POST http://localhost:8003/admin/modules/test/hello/disable | jq
curl -s -X POST http://localhost:8003/admin/modules/test/hello/enable | jq
curl -s -X POST http://localhost:8003/admin/modules/test/hello/reload | jq
```

| Test | Result | Notes |
|------|--------|-------|
| List returns enriched module data? | | |
| Get returns module detail with `module_id`? | | |
| Disable returns success? | | |
| Enable returns success? | | |
| Reload returns success? | | |

### 10.4 Credential Management

```bash
# Store credentials
curl -s -X POST http://localhost:8003/admin/modules/test/hello/credentials \
  -H 'Content-Type: application/json' \
  -d '{"credentials": {"api_key": "test-key-123"}}' | jq

# Check status
curl -s http://localhost:8003/admin/modules/test/hello | jq '.has_credentials'

# Delete credentials
curl -s -X DELETE http://localhost:8003/admin/modules/test/hello/credentials | jq
```

| Test | Result | Notes |
|------|--------|-------|
| Store credentials → success? | | |
| `has_credentials` shows `true`? | | |
| Delete credentials → success? | | |
| `has_credentials` shows `false` after delete? | | |

---

## 11. Dashboard Service API

**URL**: http://localhost:8001

### 11.1 Core Endpoints

```bash
curl -s http://localhost:8001/health | jq
curl -s http://localhost:8001/docs  # Swagger UI
curl -s http://localhost:8001/adapters | jq
curl -s http://localhost:8001/modules | jq
```

| Endpoint | Returns data? | Notes |
|----------|--------------|-------|
| `/health` | | |
| `/docs` (Swagger UI loads?) | | |
| `/adapters` (lists adapter categories?) | | |
| `/modules` (lists dynamic modules?) | | |

### 11.2 Context Endpoints

```bash
curl -s http://localhost:8001/context | jq 'keys'
curl -s http://localhost:8001/context/finance | jq
curl -s http://localhost:8001/context/weather | jq
curl -s http://localhost:8001/context/gaming | jq
curl -s http://localhost:8001/alerts/default | jq
```

| Endpoint | Returns data? | Notes |
|----------|--------------|-------|
| `/context` (unified, all categories) | | |
| `/context/finance` | | |
| `/context/weather` (requires API key) | | |
| `/context/gaming` (requires API key) | | |
| `/alerts/default` | | |

### 11.3 SSE Pipeline Stream

```bash
# Should receive JSON events every ~2s
curl -N http://localhost:8001/stream/pipeline-state
# (Ctrl+C to stop)
```

| Test | Result | Notes |
|------|--------|-------|
| SSE stream connects? | | |
| Receives JSON events with service health? | | |
| Updates every ~2 seconds? | | |

---

## 12. MCP Bridge Service

**URL**: http://localhost:8100

### 12.1 Endpoints

```bash
curl -s http://localhost:8100/health | jq
curl -s http://localhost:8100/tools | jq
curl -s http://localhost:8100/metrics | jq
```

| Endpoint | Returns data? | Notes |
|----------|--------------|-------|
| `/health` | | |
| `/tools` (lists MCP tools?) | | |
| `/metrics` | | |

### 12.2 Tool Invocation

```bash
curl -s -X POST http://localhost:8100/tools/query_agent \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"query": "What is 2+2?"}}' | jq
```

| Test | Result | Notes |
|------|--------|-------|
| Response received? | | |
| Answer correct? | | |
| Response time acceptable? | | |

---

## 13. Context Compaction

> Triggers when conversation history exceeds token window.

| Test | Result | Notes |
|------|--------|-------|
| Send 15+ messages in one conversation | | |
| Check orchestrator logs for "compacting context" (`make logs-orchestrator`) | | |
| Compaction triggered? | | |
| Agent still remembers early context? | | |
| Ask about something from start of conversation → recalls via ChromaDB? | | |

---

## 14. Observability Stack

### 14.1 Grafana Dashboards

**URL**: http://localhost:3001 (admin / admin)

| Dashboard | Loads? | Data visible? | Notes |
|-----------|--------|---------------|-------|
| gRPC LLM Overview (`grpc-llm-overview`) | | | |
| NEXUS Module System (`nexus-modules`) | | | |
| Service Health (`service-health`) | | | |
| Provider Comparison (`provider-comparison`) | | | |
| Tool Execution (`tool-execution`) | | | |

### 14.2 Prometheus

**URL**: http://localhost:9090

| Test | Result | Notes |
|------|--------|-------|
| Prometheus UI loads? | | |
| Status → Targets: all show UP? | | |
| Query `up` returns results? | | |
| Query `grpc_llm_request_duration_seconds_count` returns data? | | |

### 14.3 Monitoring Page (UI)

**URL**: http://localhost:5001/monitoring

| Test | Result | Notes |
|------|--------|-------|
| Page loads? | | |
| Grafana iframe renders dashboards? | | |
| Tab switching between dashboards works? | | |

### 14.4 Logs

```bash
make logs-orchestrator  # Tail orchestrator logs
make logs-errors        # Show error-level logs
make logs-debug         # Show debug-level logs
```

| Test | Result | Notes |
|------|--------|-------|
| `make logs-orchestrator` streams logs? | | |
| `make logs-errors` shows WARNING+ entries? | | |
| Error messages are clear and actionable? | | |

---

## 15. Automated Tests

### 15.1 Unit Tests

```bash
export PYTHONPATH=$PWD:$PYTHONPATH
pytest tests/unit/ -v
```

| Test | Result | Notes |
|------|--------|-------|
| All unit tests pass? | | |
| Failures (list any): | | |

### 15.2 Integration Tests

```bash
pytest tests/integration/ -v
```

| Test | Result | Notes |
|------|--------|-------|
| All integration tests pass? | | |
| Failures (list any): | | |

### 15.3 Showroom Integration

```bash
make showroom
```

| Test | Result | Notes |
|------|--------|-------|
| All showroom checks pass? | | |
| Total passed / total tests? | ___/___ | |

### 15.4 Full Demo

```bash
make nexus-demo
```

| Test | Result | Notes |
|------|--------|-------|
| Tests run and pass? | | |
| Pipeline UI opens in browser? | | |
| Grafana NEXUS dashboard opens? | | |

---

## 16. Docker Rebuild Reference

### When to Rebuild

| What changed? | Action | Command |
|---------------|--------|---------|
| Python source (`orchestrator/*.py`, etc.) | Rebuild service | `make quick-orchestrator` |
| `requirements.txt` / new pip dep | Rebuild no-cache | `make rebuild-orchestrator` |
| `docker-compose.yaml` env/ports only | Recreate | `make restart-orchestrator` |
| Config files (`.env`, Grafana provisioning) | Restart | `make restart-<service>` |
| Next.js / UI code | Rebuild | `make quick-ui_service` |
| Proto files (`shared/proto/`) | Regen + rebuild | `make proto-gen && make rebuild-all` |
| Everything / branch switch | Full rebuild | `make rebuild-all` |

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| Service shows **Exited (1)** | `make logs-<svc>` then fix + `make quick-<svc>` |
| Code changes not reflected | `make rebuild-<svc>` (no-cache) |
| "Module not found" error | `make rebuild-all` |
| Port already in use | `make down && make up` |
| Grafana dashboards empty | `make restart-grafana` |
| UI stuck on old version | `make quick-ui_service` |
| `.env` changes not picked up | `make restart` (no rebuild) |
| All services unhealthy | `make down && make start` |

---

## 17. Overall Assessment

### Feature Status Matrix

| # | Feature | Working? | Rating (1-5) | Needs Work? | Notes |
|---|---------|----------|--------------|-------------|-------|
| 1 | Landing page + navigation | | | | |
| 2 | Chat UI (basic conversation) | | | | |
| 3 | Math tool (math_solver) | | | | |
| 4 | Code execution (sandbox) | | | | |
| 5 | Knowledge search (ChromaDB) | | | | |
| 6 | Web search (Serper) | | | | |
| 7 | Dashboard (unified widgets) | | | | |
| 8 | Finance dashboard (Chart.js) | | | | |
| 9 | Finance widget filtering | | | | |
| 10 | Weather integration | | | | |
| 11 | Gaming integration | | | | |
| 12 | Integrations page | | | | |
| 13 | Credential hot-reload | | | | |
| 14 | Settings / provider management | | | | |
| 15 | LIDM multi-model routing | | | | |
| 16 | Context compaction | | | | |
| 17 | Pipeline UI (React Flow + SSE) | | | | |
| 18 | NEXUS module system | | | | |
| 19 | Module builder (LLM-driven) | | | | |
| 20 | Admin API (config + module CRUD) | | | | |
| 21 | MCP Bridge | | | | |
| 22 | Grafana dashboards (5) | | | | |
| 23 | Prometheus metrics | | | | |
| 24 | Monitoring page (embedded Grafana) | | | | |
| 25 | Showroom demo | | | | |
| 26 | Unit tests | | | | |
| 27 | Integration tests | | | | |

### Critical Issues Found

| # | Issue | Severity (1-5) | Steps to Reproduce |
|---|-------|----------------|---------------------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

### Usability Issues

| # | Issue | Affected Feature | Suggestion |
|---|-------|------------------|------------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

### Missing Features

| # | Expected Feature | Priority | Notes |
|---|-----------------|----------|-------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

### Performance Observations

| Area | Observation | Acceptable? |
|------|-------------|-------------|
| Service startup time | | |
| Chat response latency | | |
| Dashboard load time | | |
| Finance chart rendering | | |
| Docker resource usage | | |

### Overall Ratings

| Category | Rating (1-5) |
|----------|--------------|
| Functionality | |
| Reliability | |
| Performance | |
| Usability | |
| Documentation | |
| **Overall** | |

### Top 3 Improvements Recommended

1. _______________________________________________

2. _______________________________________________

3. _______________________________________________

### Additional Comments

```
(Write any additional feedback here)




```

---

**Thank you for testing! Save this file and share with the development team.**
