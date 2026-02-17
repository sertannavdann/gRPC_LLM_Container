# Live Data Audit — Tool & Adapter Sprawl Analysis

**Captured:** 2026-02-17 from running Docker services

## Pipeline SSE Snapshot (live)

### Services (5)
| Service | State | Latency |
|---------|-------|---------|
| dashboard | running | 0ms |
| orchestrator_admin | running | 8ms |
| llm_service | unknown | 0ms |
| chroma_service | unknown | 0ms |
| sandbox_service | unknown | 0ms |

### Adapters (12 registered, only 5 with real backends)
| Adapter | State | Auth | Creds | Notes |
|---------|-------|------|-------|-------|
| finance/mock | running | - | yes | **Redundant** — mock overlaps cibc |
| finance/cibc | running | - | yes | Real adapter |
| calendar/mock | running | - | yes | **Redundant** — mock only |
| calendar/google_calendar | running | auth | NO | Real but no creds |
| health/mock | running | - | yes | **Mock-only** — no real adapter exists |
| navigation/mock | running | - | yes | **Mock-only** — no real adapter exists |
| weather/openweather | running | auth | NO | Real but no creds |
| weather/open-meteo | running | - | yes | Dynamic module |
| gaming/clashroyale | running | auth | NO | Real but no creds |
| test/srccheck | running | auth | NO | Test module |
| test/hello | running | - | yes | Test module |
| showroom/metrics_demo | running | - | yes | Demo module |

### Tools (27 registered — 14 exposed to LLM)
| # | Tool | File | Lines | Concern |
|---|------|------|-------|---------|
| 1 | web_search | web_search.py | 149 | General utility — OK |
| 2 | math_solver | math_solver.py | 266 | General utility — OK |
| 3 | load_web_page | web_loader.py | 231 | General utility — OK |
| 4 | **get_user_context** | user_context.py | 412 | **OVERLAP: fetches same data as context_bridge for ALL 6 categories** |
| 5 | **get_daily_briefing** | user_context.py | - | **REDUNDANT: calls get_user_context(["all"])** |
| 6 | **get_commute_time** | user_context.py | - | **REDUNDANT: subset of get_user_context(["navigation"])** |
| 7 | search_knowledge | knowledge_search.py | 125 | ChromaDB RAG — OK but chroma_service is unknown |
| 8 | store_knowledge | knowledge_search.py | - | ChromaDB RAG — OK but chroma_service is unknown |
| 9 | execute_code | code_executor.py | 128 | Sandbox exec — OK but sandbox_service is unknown |
| 10 | **query_finance** | finance_query.py | 212 | **OVERLAP: duplicates finance data already in context_bridge** |
| 11 | build_module | module_builder.py | 669 | NEXUS build pipeline |
| 12 | write_module_code | module_builder.py | - | NEXUS build pipeline |
| 13 | repair_module | module_builder.py | - | NEXUS build pipeline |
| 14 | validate_module | module_validator.py | 579 | NEXUS validation |
| 15 | list_modules | module_manager.py | 186 | NEXUS management |
| 16 | enable_module | module_manager.py | - | NEXUS management |
| 17 | disable_module | module_manager.py | - | NEXUS management |
| 18 | store_module_credentials | module_manager.py | - | NEXUS management |
| 19 | install_module | module_installer.py | 321 | NEXUS install |
| 20 | uninstall_module | module_installer.py | - | NEXUS install |
| 21 | create_draft | (draft/version) | - | NEXUS drafts |
| 22 | edit_draft | (draft/version) | - | NEXUS drafts |
| 23 | diff_draft | (draft/version) | - | NEXUS drafts |
| 24 | validate_draft | (draft/version) | - | NEXUS drafts |
| 25 | promote_draft | (draft/version) | - | NEXUS drafts |
| 26 | list_versions | (draft/version) | - | NEXUS versioning |
| 27 | rollback_version | (draft/version) | - | NEXUS versioning |

### Unregistered but loaded
| File | Lines | Status |
|------|-------|--------|
| destinations.py | 137 | **Dead code** — imported by user_context inline but not registered as tool |
| feature_test_harness.py | 253 | **Dead code** — not registered, no call path from orchestrator |
| chart_validator.py | 379 | **Dead code** — not registered |
| context_bridge.py | 188 | Internal bridge — not a tool, called by user_context |

## SOLID Violations Identified

### 1. Single Responsibility Violation (SRP)
- **context_bridge.py** fetches ALL 6 adapter categories AND normalizes data shapes
- **user_context.py** re-fetches the same data, has its own mock, its own formatter, AND 3 separate tools that are just parameter variations of the same function
- **finance_query.py** duplicates finance access that context_bridge already provides

### 2. Open-Closed Violation (OCP)
- Adding a new adapter category (e.g., fitness/strava) requires editing:
  - `context_bridge.py` _normalize_context_for_tools() — hardcoded 6-category switch
  - `user_context.py` _get_mock_context() — hardcoded mock data
  - `user_context.py` _build_fallback_summary() — hardcoded category list
  - `pipeline_stream.py` — hardcoded adapter builder
- **Should be**: adapter registers itself, context bridge discovers it

### 3. Interface Segregation Violation (ISP)
- LLM is exposed to 27 tools. Module build/validate/install/repair are 4 separate tools that the LLM must choose between correctly. Draft lifecycle is 7 tools.
- **Should be**: Coarse-grained composite tools (`module_pipeline`, `draft_lifecycle`) that the LLM invokes with an `action` parameter

### 4. Dependency Inversion Violation (DIP)
- user_context.py hardcodes `from .context_bridge import fetch_context_sync`
- finance_query.py hardcodes `DASHBOARD_URL` and makes raw HTTP calls
- Both tools contain duplicate mock data fallbacks instead of a single mock provider

## Redundancy Map

```
context_bridge ──fetches──→ /context (ALL 6 categories)
     │
     ├── user_context.get_user_context() ──re-fetches──→ same /context
     │      ├── get_daily_briefing() ──calls──→ get_user_context(["all"])  ← REDUNDANT
     │      └── get_commute_time() ──calls──→ fetch_context_sync(["navigation"]) ← REDUNDANT
     │
     └── finance_query.query_finance() ──fetches──→ /bank/* ← PARALLEL PATH

destinations.py ── never called from orchestrator ← DEAD
feature_test_harness.py ── never called from orchestrator ← DEAD
chart_validator.py ── never called from orchestrator ← DEAD
```

## Adapter Mock Sprawl

- 4 mock adapters running (finance, calendar, health, navigation) — all produce synthetic data
- user_context.py has its OWN inline mock data (_get_mock_context) — a 5th mock source
- Mock adapters should be dev-only, not production-registered

## Proposed Consolidation Targets

1. **Collapse user_context + context_bridge + destinations → single `user_context` tool** with category parameter
2. **Absorb finance_query into user_context** as action="finance_query" or keep as standalone but remove overlap
3. **Remove get_daily_briefing, get_commute_time** — they're just get_user_context with preset params
4. **Consolidate module tools**: build+write+repair → `module_build_pipeline`; install+uninstall → `module_lifecycle`; draft tools → `draft_manager`
5. **Remove dead code**: destinations.py (inline), feature_test_harness.py, chart_validator.py
6. **Mock adapter gating**: disable mock adapters when real ones have credentials
