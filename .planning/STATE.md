# NEXUS — Current State

> **GSD Canonical File** | Auto-generated 2026-02-15 from `docs/**`

---

## Current Phase

**Phase 0 (Foundation)** — complete. Next up: **Phase 1 — Auth Boundary** then **Phase 3 — Self-Evolution Engine** (the project's core differentiator).

---

## What's Done

### Track A: Self-Evolving Module Infrastructure
- **A1 ✅** Module manifest schema, dynamic loader (`importlib`), SQLite registry
- **A2 ✅** Fernet credential store with encryption at rest
- **A3 ✅** Agent tool integration (`build_module`, `install_module` tools registered)
- **A4 🚧** LLM-driven module builder — stub implemented, template generation in progress

### Track B: Observability & Control
- **B1 ✅** Prometheus metrics, `ModuleMetrics` dataclass
- **B2 ✅** Admin API v1 (routing config hot-reload)
- **B3 ✅** Admin API v2 (module CRUD, credentials management)
- **B4 ✅** Pipeline UI with SSE streaming, React Flow visualization

### Completed Integrations
- ✅ OpenWeather API (weather)
- ✅ Google Calendar OAuth2 (calendar)
- ✅ Clash Royale API (gaming)
- ✅ CIBC CSV files (finance)
- ✅ Showroom metrics demo (test)

### Infrastructure
- ✅ 13-container Docker Compose stack (`docker compose up` → running in <10 min)
- ✅ Unified orchestrator (replaced supervisor-worker mesh, Jan 2026)
- ✅ LIDM routing: Standard (0.5B) / Heavy (14B) tiers
- ✅ Context bridge (HTTP-based orchestrator ↔ dashboard)
- ✅ Sandbox service (gRPC, process-isolated code execution)
- ✅ ChromaDB RAG integration
- ✅ cAdvisor container monitoring
- ✅ Grafana NEXUS Modules dashboard + alert rules

---

## What's In Progress

| Item | Status | Blocker |
|------|--------|---------|
| LLM-driven module builder (Track A4) | Template generation WIP | Need to wire sandbox validation loop |
| Pipeline UI drag-and-drop | Design phase | — |
| GSD planning bootstrap | **This milestone** | — |

---

## Open Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **No auth on Admin API or Dashboard** | HIGH | Phase 1 (REQ-001/002) is first priority; currently any HTTP client can modify config, modules, and credentials |
| **No approval gates for module install** | HIGH | Malicious adapter code can be enabled without review; mitigated partially by sandbox validation (once A4 complete) |
| **No automated tests for Admin API CRUD** | MEDIUM | Regressions from refactoring go undetected; manual curl testing only |
| **Dashboard SRP violation** | MEDIUM | Single service handles 5+ concerns; harder to scale and test independently |
| **No rate limiting** | MEDIUM | All HTTP endpoints vulnerable to abuse/DoS |
| **SQLite is sufficient for now** | LOW | Module registry, credentials, checkpoints all on SQLite; good enough for local development — scaling migration deferred |

---

## Known Gaps

1. **Commercial features are 0% implemented** — auth, billing, audit, marketplace documented as ideation only; all current development is open-source first (detailed in `docs/archive/PLAN.md`).
2. **Track C (Co-Evolution)** — Curriculum Agent, Executor Agent, approval gates: 0% complete, planned Q2 2026.
3. **Multi-tenant isolation** not implemented — single-tenant only.
4. **No E2E tests** for Pipeline UI SSE reconnection.
5. **No centralized logging** — logs are per-container, searched via `docker-compose logs`.

---

## Codebase Metrics (Approximate)

| Metric | Value |
|--------|-------|
| Services | 7 (orchestrator, dashboard, UI, LLM, chroma, sandbox, bridge) |
| Docker containers | 13 (7 services + Prometheus + Grafana + cAdvisor + OTel + Tempo + postgres placeholder) |
| Installed modules | 4 (weather, calendar, gaming, finance) + 1 showroom |
| Unit tests | ~270 |
| Integration tests | ~96 |
| Lines of code (Python) | ~15,000 |
| docs/ files | 11 current + 7 archive |

---

## Progress Snapshot

> Placeholder for `gsd-tools progress table` output.

```
Phase                          Status        Requirements  Done  Remaining
─────────────────────────────  ──────────    ────────────  ────  ─────────
Phase 0: Foundation            complete      —             —     —
Phase 1: Auth Boundary         not-started   3             0     3
Phase 2: Run-Unit Metering     not-started   4             0     4
Phase 3: Self-Evolution Engine not-started   2             0     2
Phase 4: Release-Quality       not-started   2             0     2
Phase 5: Audit Trail           not-started   3             0     3
Phase 6: Co-Evolution          not-started   4             0     4
Phase 7: Enterprise & Market   not-started   12            0     12
─────────────────────────────  ──────────    ────────────  ────  ─────────
TOTAL                                        30            0     30
```
