# NEXUS — Project Definition

> **GSD Canonical File** | Auto-generated 2026-02-15 from `docs/**`

---

## What NEXUS Is

**NEXUS** (Neural EXtensible Unified System) is a **self-evolving, multi-provider LLM agent platform** built on gRPC microservices. It orchestrates AI agents that can build, test, and deploy their own integration modules at runtime — turning natural-language requests ("track my Clash Royale stats") into production adapters without human coding (although enabling developer mode will be able to review the code and have instructional reviews on how the modules are working.) 

### Core Architecture

- **Unified Orchestrator** — single coordination service with LangGraph state machine, LIDM (Language-Integrated Decision Making) routing, tool calling, and context bridge.
- **Module System** — hot-swappable adapters loaded dynamically via `importlib`, persisted in SQLite registry, with Fernet-encrypted credential store.
- **Observability Stack** — Prometheus metrics, Grafana dashboards, cAdvisor container monitoring, OpenTelemetry traces.
- **Sandbox** — process-isolated gRPC service for untrusted code execution during module validation.
- **Multi-Provider LLM** — local inference (llama.cpp), plus OpenAI/Anthropic/Perplexity pass-through; LIDM routes by complexity tier (Standard 0.5B / Heavy 14B / Ultra reserved).

### Target Users

1. **AI/ML platform teams** at Series A–C startups shipping agents to production.
2. **DevOps / SRE teams** adding AI workflows with observability requirements.
3. **Solo developers / AI hackers** building on local-first inference.
4. **Enterprise IT** in regulated industries needing audit trails, RBAC, and compliance.

### Business Model (Future — Ideation Only)

All essential development is **open-source first**. Commercial tiers are documented for strategic planning but are not near-term deliverables.

*Planned tiers*: Free (OSS runtime + local inference) → Team ($49–99/seat, RBAC, secrets, 90-day traces) → Enterprise ($30k–250k/yr, SSO, audit, SLA). Module marketplace with 85/15 creator/platform split at launch. See [docs/MONETIZATION_STRATEGY.md](../docs/MONETIZATION_STRATEGY.md) for the full ideation.

---

## Non-Goals

- **Training / fine-tuning LLMs** — NEXUS orchestrates inference, it does not train models.
- **Replacing general-purpose CI/CD** — module build/test is scoped to adapter code only.
- **No-code visual programming** — the UI visualizes pipelines but code generation is LLM-driven, not drag-and-drop logic.
- **Mobile-first** — desktop/server-first; mobile apps are long-term.

---

## Hard Constraints

| Constraint | Rationale |
|---|---|
| **gRPC for inter-service comms** | Type-safe protobuf contracts, streaming, binary efficiency. Retrofit cost to REST-based competitors is prohibitive. |
| **Docker Compose as deployment unit** | 13-container stack; single `docker compose up` from zero to running system in <10 min. |
| **Python-only adapters** | Module loader uses `importlib`; all adapters extend `BaseAdapter[T]`. No polyglot runtime planned. |
| **SQLite for all state stores** | Module registry, credential store, checkpoints. Good enough for local development; scaling migration deferred until user base warrants it. |
| **Local-first inference default** | llama.cpp via gRPC; no mandatory cloud dependency. Cloud providers are opt-in. |
| **Single orchestrator (no mesh)** | Unified orchestrator replaced supervisor-worker mesh in Jan 2026. Design decision is final. |

---

## Key Dependencies

| Dependency | Role |
|---|---|
| LangGraph | Agent state machine (core/graph.py) |
| llama.cpp (llama-cpp-python) | Local LLM inference |
| FastAPI | Admin API (:8003), Dashboard (:8001) |
| ChromaDB | Vector DB for RAG |
| Prometheus + Grafana + cAdvisor | Observability |
| Fernet (cryptography.io) | Credential encryption at rest |
| Next.js 14 | UI service |
| React Flow | Pipeline visualization |

---

## Source Documents

- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — current system state
- [docs/NEXUS_LEAN_CANVAS.md](../docs/NEXUS_LEAN_CANVAS.md) — value proposition & market
- [docs/MONETIZATION_STRATEGY.md](../docs/MONETIZATION_STRATEGY.md) — pricing & go-to-market
- [docs/archive/PROJECT_VISION.md](../docs/archive/PROJECT_VISION.md) — original aspirational design
