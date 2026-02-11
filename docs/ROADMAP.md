# NEXUS Roadmap

**Last Updated**: February 2026

## Overview

NEXUS is evolving from a multi-agent LLM framework to a **self-evolving system** that can build, test, and deploy its own modules.

---

## Version History

### v3.0 - NEXUS Foundation (Feb 2026) ✅

**Track A: Self-Evolving Module Infrastructure**
- ✅ A1: Module manifest schema, loader, SQLite registry
- ✅ A2: Fernet credential store with encryption at rest
- ✅ A3: Agent tool integration (build_module, install_module tools)
- 🚧 A4: LLM-driven module builder (in progress)

**Track B: Observability & Control**
- ✅ B1: Prometheus metrics, ModuleMetrics dataclass
- ✅ B2: Admin API v1 (routing config hot-reload)
- ✅ B3: Admin API v2 (module CRUD, credentials management)
- ✅ B4: Pipeline UI with SSE streaming, React Flow visualization

**Real Adapter Integrations**
- ✅ OpenWeather API (weather)
- ✅ Google Calendar OAuth2 (calendar)
- ✅ Clash Royale API (gaming)
- ✅ CIBC CSV files (finance)

**Infrastructure**
- ✅ cAdvisor container monitoring
- ✅ Grafana NEXUS Modules dashboard
- ✅ Prometheus alert rules
- ✅ Showroom integration tests

### v2.0 - Unified Orchestrator (Jan 2026) ✅

- ✅ Replace supervisor-worker mesh with unified orchestrator
- ✅ LIDM (Language-Integrated Decision Making) routing
- ✅ Context bridge (HTTP-based orchestrator ↔ dashboard)
- ✅ Tool calling improvements (plain-text synthesis)
- ✅ ChromaDB RAG integration
- ✅ Bank data integration (CIBC CSV adapter)

### v1.0 - Multi-Agent Foundation (Dec 2025) ✅

- ✅ gRPC service architecture
- ✅ LLM service (llama.cpp)
- ✅ ChromaDB vector database
- ✅ Sandbox service (code execution)
- ✅ Dashboard service (FastAPI)
- ✅ UI service (Next.js)
- ✅ Adapter registry pattern

---

## Current Sprint (Feb 2026)

### In Progress

**Track A4: LLM-Driven Module Builder** 🚧
- [ ] Implement `build_module` tool with template generation
- [ ] LLM-driven code generation from natural language specs
- [ ] Sandbox validation before installation
- [ ] Automated test generation
- [ ] Error feedback loop for self-correction

**Pipeline UI Enhancements** 🚧
- [ ] Node drag-and-drop customization
- [ ] Real-time module status updates
- [ ] Error visualization with logs
- [ ] Performance metrics overlay

**Testing** 🚧
- [ ] E2E tests for Pipeline UI SSE reconnection
- [ ] Admin API CRUD integration tests
- [ ] Module loader edge case coverage
- [ ] Credential store security audit

---

## Q2 2026 - Track C: Co-Evolution

### C1: Curriculum Agent (Planned)

**Goal**: Agent that identifies missing capabilities and proposes new modules.

**Features**:
- Analyze user conversation history
- Identify capability gaps (e.g., "User asked about stocks, but no finance API")
- Propose module specifications
- Prioritize by user needs

**Status**: 📋 Design phase

### C2: Executor Agent (Planned)

**Goal**: Agent that implements modules proposed by Curriculum Agent.

**Features**:
- Generate module code from specifications
- Write unit tests
- Deploy to sandbox for validation
- Submit for approval gate

**Status**: 📋 Design phase

### C3: Approval Gates (Planned)

**Goal**: UI for user approval of module installations.

**Features**:
- Review module code before installation
- Inspect required credentials
- View sandbox test results
- Approve/reject with feedback

**Status**: 📋 Design phase

---

## Q3 2026 - Multi-Tenant & Security

### Authentication & Authorization
- [ ] OAuth2 for Admin API
- [ ] API key authentication for Dashboard API
- [ ] JWT tokens for gRPC services
- [ ] Role-based access control (RBAC)
- [ ] Audit logging for sensitive operations

### Multi-Tenant Support
- [ ] User isolation in module registry
- [ ] Per-user credential stores
- [ ] Tenant-scoped module installations
- [ ] Usage quotas and rate limiting

### Module Marketplace
- [ ] Public module registry (read-only)
- [ ] Community module submissions
- [ ] Module versioning and updates
- [ ] Security scanning for community modules

---

## Q4 2026 - Performance & Scalability

### Horizontal Scaling
- [ ] Stateless orchestrator design
- [ ] Redis session store
- [ ] Load balancing across orchestrator instances
- [ ] Distributed module registry

### Performance Optimizations
- [ ] Adapter result caching (Redis)
- [ ] Context aggregation parallelization
- [ ] LLM response streaming optimizations
- [ ] Database query optimization

### Reliability
- [ ] Service health checks and auto-restart
- [ ] Circuit breakers for external APIs
- [ ] Graceful degradation (fallback modes)
- [ ] Disaster recovery procedures

---

## 2027 - Advanced Features

### Agent Mesh v2
- [ ] Specialized agents (researcher, coder, planner)
- [ ] Agent-to-agent communication protocols
- [ ] Hierarchical task delegation
- [ ] Consensus mechanisms for multi-agent decisions

### LLM Provider Abstraction
- [ ] OpenAI API support
- [ ] Anthropic API support
- [ ] Perplexity API support
- [ ] Dynamic provider selection based on task type

### Advanced Adapters
- [ ] Real-time data streaming adapters
- [ ] Webhook-based event adapters
- [ ] GraphQL API adapters
- [ ] Database CDC (Change Data Capture) adapters

### Natural Language Configuration
- [ ] "Add OpenWeather with my API key" → auto-install
- [ ] "Show me my spending this month" → auto-query finance
- [ ] "Remind me about meetings today" → auto-enable calendar

---

## Feature Requests (Community-Driven)

### Short-Term (Next 3 Months)
- [ ] Module rollback (previous version restore)
- [ ] Module dependency management
- [ ] Adapter health monitoring dashboard
- [ ] Credential expiration warnings
- [ ] Export/import module configurations

### Medium-Term (3-6 Months)
- [ ] Mobile app (React Native)
- [ ] Voice interface (speech-to-text)
- [ ] Slack/Discord bot integration
- [ ] Scheduled tasks (cron-like)
- [ ] Email digest (daily briefing)

### Long-Term (6-12 Months)
- [ ] Visual module builder (no-code)
- [ ] AI-powered module recommendations
- [ ] Federated learning across users
- [ ] Cross-platform mobile/desktop sync

---

## Technical Debt

See [KNOWN-ISSUES.md](./KNOWN-ISSUES.md) for current technical debt items.

### High Priority
1. Admin API CRUD operations lack automated tests
2. Dashboard service violates SRP (too many concerns)
3. Finance categorizer uses hardcoded regex (OCP violation)
4. No E2E tests for Pipeline SSE reconnection

### Medium Priority
1. Module builder tool not yet implemented
2. No approval gates for module installation
3. Credential validation logic scattered across services
4. No module versioning or rollback

### Low Priority
1. No rate limiting on API endpoints
2. Missing API versioning (implicit v1)
3. No caching for expensive adapter calls
4. Logs not centralized (ELK stack)

---

## Completed Milestones

### February 2026
- ✅ Pipeline UI with React Flow and SSE
- ✅ Admin API v2 with module CRUD
- ✅ Showroom integration tests
- ✅ cAdvisor container monitoring
- ✅ Grafana NEXUS dashboard
- ✅ Context formatter refactoring (SRP)

### January 2026
- ✅ NEXUS module system foundation
- ✅ Credential store with Fernet encryption
- ✅ Module loader and registry
- ✅ Real adapter integrations (weather, calendar, gaming)

### December 2025
- ✅ Unified orchestrator (replaced supervisor-worker)
- ✅ LIDM routing system
- ✅ Bank data integration (CIBC CSV)
- ✅ Context bridge HTTP migration

---

## Success Metrics

### Module System
- **Current**: 4 modules (weather, calendar, gaming, showroom)
- **Q2 2026 Target**: 10 modules (50% community-contributed)
- **Q4 2026 Target**: 25 modules (75% community-contributed)

### Performance
- **Current**: Standard tier ~500ms, Heavy tier ~2s
- **Q2 2026 Target**: Standard ~300ms, Heavy ~1.5s
- **Q4 2026 Target**: Standard ~200ms, Heavy ~1s

### Reliability
- **Current**: 95% uptime (development)
- **Q2 2026 Target**: 99% uptime (beta)
- **Q4 2026 Target**: 99.9% uptime (production)

### Adoption
- **Current**: Internal development only
- **Q2 2026 Target**: 10 beta users
- **Q4 2026 Target**: 100 active users

---

## Contributing

See [EXTENSION-GUIDE.md](./EXTENSION-GUIDE.md) for how to build modules and contribute to NEXUS.

---

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - Current system state
- [KNOWN-ISSUES.md](./KNOWN-ISSUES.md) - Technical debt
- [PROJECT_VISION.md](./archive/PROJECT_VISION.md) - Original aspirational design
