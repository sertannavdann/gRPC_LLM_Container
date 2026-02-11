# Archive Index

Historical documentation kept for reference. These documents may not reflect the current implementation state.

For **current documentation**, see the main [docs/](../README.md) directory.

---

## Archived Documents

### PROJECT_VISION.md
**Date**: Original design (2025)
**Status**: Aspirational (partially implemented)

Original vision for NEXUS as a self-evolving system. Key concepts:
- Self-evolution via Curriculum and Executor agents (Track C, planned Q2 2026)
- Module marketplace (planned Q3 2026)
- Natural language configuration (planned 2027)

**Current State**: Track A (infrastructure) 75% complete, Track B (observability) 100% complete, Track C (co-evolution) 0% complete.

**Reference**: Historical context for Track C planning.

---

### PLAN.md
**Date**: Detailed tier 1-5 roadmap (2025)
**Status**: Active reference

Comprehensive implementation plan with 5 tiers:
- Tier 1: Foundation (✅ complete)
- Tier 2: Core Services (✅ complete)
- Tier 3: Advanced Features (🚧 in progress)
- Tier 4: Optimization (📋 planned)
- Tier 5: Production (📋 planned)

**Reference**: Detailed task breakdowns for roadmap milestones.

---

### HIGH_LEVEL_DESIGN.md
**Date**: System design reference (2025)
**Status**: Partially outdated

Original high-level design including:
- Supervisor-worker mesh (replaced by unified orchestrator in Jan 2026)
- Agent communication patterns (simplified with LIDM)
- Tool registry design (still relevant)

**Reference**: Design patterns and architectural decisions.

---

### EXECUTION_PLAN.md
**Date**: Phase-based execution plan (2025)
**Status**: Partially complete

Detailed execution timeline with:
- Phase 1: Foundation (✅ complete)
- Phase 2: Core Features (✅ complete)
- Phase 3: Observability (✅ complete Feb 2026)
- Phase 4-5: Advanced features (🚧 in progress)

**Reference**: Timeline and milestone planning.

---

### BRANCH_SUMMARY.md
**Date**: Branch-specific change tracking (2025-2026)
**Status**: Active

Summary of changes per Git branch:
- `main`: Production releases
- `NEXUS`: Track A/B development (merged Feb 2026)
- Feature branches: Specific feature development

**Reference**: Understanding Git history and merge contexts.

---

### next-phase.md
**Date**: Advanced orchestration and HMI design (2026)
**Status**: Active planning

Design notes for:
- Advanced orchestration patterns
- Human-Machine Interface (HMI) research
- SSE, Zustand, React Flow patterns (implemented in Pipeline UI)
- Approval gates design (Track C3, planned)

**Reference**: UI/UX design patterns for future features.

---

### SUPERVISOR_WORKER_MESH.md (DELETED)
**Date**: Original multi-agent architecture (2025)
**Status**: Obsolete (deleted Feb 2026)

Described supervisor-worker mesh architecture. **Replaced by unified orchestrator in January 2026** due to:
- High message passing overhead
- Complex state synchronization
- Difficult debugging
- No clear ownership of tool results

**Reference**: Historical context only. See [ARCHITECTURE.md](../ARCHITECTURE.md) for current unified orchestrator design.

---

## Why Archive These Documents?

1. **Historical Context**: Understanding design evolution and decisions.
2. **Future Reference**: Track C (co-evolution) references PROJECT_VISION.md concepts.
3. **Lessons Learned**: Document why certain approaches were abandoned (e.g., supervisor-worker mesh).
4. **Planning**: PLAN.md and EXECUTION_PLAN.md still guide roadmap.

---

## Using Archived Documents

**Before referencing**:
- Check [ARCHITECTURE.md](../ARCHITECTURE.md) for current implementation state
- Compare archived designs with current reality
- Note discrepancies (aspirational vs. implemented)

**When planning new features**:
- Review PROJECT_VISION.md for long-term goals
- Check PLAN.md for detailed task breakdowns
- Reference HIGH_LEVEL_DESIGN.md for patterns

**When debugging**:
- Don't assume archived designs match current code
- Use [ARCHITECTURE.md](../ARCHITECTURE.md) as source of truth
- Consult Git history for actual implementation

---

## Navigation

**Current Documentation**: [docs/README.md](../README.md)

**Active Planning**:
- [ROADMAP.md](../ROADMAP.md) - Current roadmap
- [KNOWN-ISSUES.md](../KNOWN-ISSUES.md) - Technical debt

**Implementation Guides**:
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Current system
- [EXTENSION-GUIDE.md](../EXTENSION-GUIDE.md) - Building modules
- [API-REFERENCE.md](../API-REFERENCE.md) - API docs

---

## Maintenance

**Review Schedule**: Quarterly (March, June, September, December)

**Criteria for Archiving**:
- Document describes replaced/removed features
- Implementation diverged significantly from design
- Document is purely historical (no active references)

**Criteria for Deletion**:
- Document is actively misleading
- No historical value
- Fully superseded by current docs

---

## Questions?

If archived documents contradict current implementation, trust:
1. **Current code** (source of truth)
2. **[ARCHITECTURE.md](../ARCHITECTURE.md)** (documented truth)
3. **Archived docs** (historical reference)

Report documentation inconsistencies: [GitHub Issues](repository-url)
