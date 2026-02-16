---
phase: 03-self-evolution-engine
plan: 02
subsystem: llm-gateway
tags: ["providers", "routing", "validation", "budget", "fallback"]
dependency_graph:
  requires: ["03-01"]
  provides: ["github-models-provider", "llm-gateway", "purpose-routing"]
  affects: []
tech_stack:
  added: ["github-models-api", "purpose-based-routing", "schema-validation"]
  patterns: ["retry-with-backoff", "deterministic-fallback", "budget-tracking"]
key_files:
  created:
    - "shared/providers/github_models.py"
    - "shared/providers/llm_gateway.py"
    - "tests/unit/providers/test_github_models.py"
    - "tests/unit/providers/test_llm_gateway.py"
    - "tests/unit/providers/test_fallback_chain.py"
  modified:
    - "shared/providers/__init__.py"
decisions:
  - "GitHub Models inference endpoint (not Copilot IDE mode) provides structured code generation"
  - "Schema validation rejects non-conforming outputs immediately (no silent fallback)"
  - "Fallback chain is deterministic - same failure always selects same next model"
  - "Auth/schema errors trigger fallback, not retry of same model"
  - "AllModelsFailedError provides structured data for job pause recommendation"
metrics:
  duration_minutes: 7.4
  completed_at: "2026-02-16T00:21:32Z"
  tests_added: 47
  files_created: 5
  commits: 3
---

# Phase 03 Plan 02: Module Generator Gateway

**Ship the LLM provider wrapper that normalizes auth, org attribution, schema enforcement, routing, budgets, and retries.**

## One-liner

Built GitHub Models provider with retry logic and LLM Gateway with purpose-based routing, schema validation, and deterministic fallback for stable code generation.

## What Was Built

### Task 1: GitHub Models Provider Client

**Files:**
- `shared/providers/github_models.py` (414 lines)
- `tests/unit/providers/test_github_models.py` (473 lines)

**Features:**
- GitHubModelsProvider extending BaseProvider with GitHub AI inference endpoint
- Support for both standard and org-attributed billing paths
- Retry with exponential backoff for transient errors (429/5xx/timeout)
- No retry on auth errors (401/403) or client errors (400/schema)
- Structured output support via `response_format` json_schema
- Seed support for reproducible generation
- 19 unit tests with full mock coverage

**Key implementation:**
- `_retry_request()`: Bounded retry (max 3 attempts) with exponential backoff starting at 1s
- Auth errors raise `ProviderAuthError` immediately without retry
- Rate limit (429) and server errors (5xx) trigger retry
- Timeout errors also retry with backoff
- Health check endpoint for connectivity verification

### Task 2: LLM Gateway Routing Layer

**Files:**
- `shared/providers/llm_gateway.py` (513 lines)
- `tests/unit/providers/test_llm_gateway.py` (554 lines)

**Features:**
- RoutingPolicy with purpose lanes: codegen, repair, critic
- ModelPreference with priority-based ordering
- Schema validation against GeneratorResponseContract from Phase 01
- Per-request and per-job token budget tracking
- Seed support for reproducibility
- 21 unit tests covering routing, validation, and budgets

**Key implementation:**
- `generate()`: Routes to models by purpose, validates schema, tracks usage
- `_validate_schema()`: JSON parse → Pydantic validation → path allowlist check
- `_check_budget()`: Enforces max_tokens_per_request and per-job limits
- `_record_usage()`: Tracks total tokens and request count per job
- Rejects non-conforming outputs with `SchemaValidationError` (not silent fallback)
- BudgetExceededError raised before attempting generation

### Task 3: Fallback Chain + Tests

**Files:**
- `tests/unit/providers/test_fallback_chain.py` (452 lines)

**Features:**
- Deterministic fallback: same failure condition → same next model
- Priority-based model selection (0 = highest priority)
- AllModelsFailedError for structured job pause recommendation
- 7 integration-style tests verifying fallback behavior

**Key behaviors tested:**
- Rate limit triggers fallback to next provider
- Connection error triggers fallback
- Auth error triggers fallback (not retry)
- All models failing produces deterministic error with all attempts
- Fallback order exactly matches priority configuration
- Same failure always selects same next model (determinism)

## Deviations from Plan

**None** - Plan executed exactly as written.

All tasks completed:
- GitHub Models client works with attributed/unattributed endpoints ✅
- Gateway routes by purpose and enforces schema ✅
- Fallback chain is deterministic ✅
- Tests cover success, retry, timeout, auth, schema validation ✅

## Verification Results

All verification commands passed:

```bash
# Task 1: GitHub Models provider tests
cd /Users/sertanavdan/Documents/Software/AI/gRPC_llm && \
  python -m pytest tests/unit/providers/test_github_models.py -v --tb=short
# ✅ 19 passed, 2 warnings in 0.23s

# Task 2: LLM Gateway tests
cd /Users/sertanavdan/Documents/Software/AI/gRPC_llm && \
  python -m pytest tests/unit/providers/test_llm_gateway.py -v --tb=short
# ✅ 21 passed, 2 warnings in 0.08s

# Task 3: Fallback chain tests
cd /Users/sertanavdan/Documents/Software/AI/gRPC_llm && \
  python -m pytest tests/unit/providers/test_fallback_chain.py -v --tb=short
# ✅ 7 passed, 2 warnings in 0.06s
```

## Success Criteria Met

✅ **Gateway stable enough for builder orchestrator in Wave 2**
- Purpose-based routing works with configurable model preferences
- Schema validation rejects garbage outputs before they enter validation
- Budget tracking prevents runaway token usage
- Deterministic fallback provides predictable behavior

✅ **REQ-013: Programmatic module generation engine exists**
- Backend-compatible inference surface via GitHub Models provider
- Structured outputs enforced via `response_format` json_schema
- Gateway provides stable API for builder to call

✅ **REQ-016: Deterministic schema enforcement**
- GeneratorResponseContract validated before returning to caller
- Non-conforming outputs trigger fallback, not silent acceptance
- Path allowlist prevents modifications outside module directory
- Markdown fence detection in FileChange content validation

## Integration Notes

**Gateway not yet wired into orchestrator** - Task 3 only created tests for fallback behavior. Actual orchestrator integration deferred to Wave 2 (Plan 03-03 or later) when builder orchestrator is ready.

Current state:
- GitHubModelsProvider registered in `shared/providers/__init__.py`
- LLMGateway exists as standalone module
- Orchestrator still uses existing provider routing via `setup_providers()`

**Next step:** Plan 03-03 will wire gateway into builder for actual module generation.

## Architecture Decisions

### 1. Schema validation rejects, not repairs

**Choice:** Non-conforming LLM output raises `SchemaValidationError` and triggers fallback.

**Rationale:** Silent repair hides model quality issues. Explicit rejection enables:
- Tracking which models produce valid outputs
- Falling back to better-performing models
- Surfacing schema violations for prompt tuning

**Alternative rejected:** Auto-repair with default values could mask bugs in prompts.

### 2. Deterministic fallback order

**Choice:** Priority order is fixed, always selects same next model for same failure.

**Rationale:**
- Predictable behavior for debugging
- Enables testing with mocked providers
- Avoids race conditions in concurrent requests

**Implementation:** Preferences sorted by priority once at policy creation, not per-request.

### 3. Budget enforcement before generation

**Choice:** Check budget before calling provider, not after.

**Rationale:**
- Prevents wasted API calls when budget exceeded
- Fails fast with clear error message
- Per-job tracking allows progressive budget consumption across multiple calls

**Implementation:** `_check_budget()` called at start of `generate()`, before provider selection.

## Test Coverage

**47 total tests** across 3 test files:

- **test_github_models.py (19 tests):**
  - Initialization, header building, endpoint construction
  - Payload building with schema and seed
  - Response parsing
  - Success, auth error, rate limit retry, timeout retry
  - Server error retry, client error no-retry
  - Health check

- **test_llm_gateway.py (21 tests):**
  - Routing policy creation and preference retrieval
  - Provider registration
  - Budget setting and tracking
  - Per-request and per-job budget enforcement
  - Schema validation (success, invalid JSON, missing fields, disallowed paths)
  - Generation success, fallback on error, all models fail
  - Job budget tracking
  - Seed support
  - Routing info retrieval

- **test_fallback_chain.py (7 tests):**
  - Fallback on rate limit, connection error, auth error
  - All models fail produces deterministic error
  - Fallback order matches priority
  - Same failure always selects same next model
  - Job pause recommendation on all fail

## Known Limitations

1. **Streaming not implemented** - `generate_stream()` falls back to non-streaming for now
2. **Orchestrator wiring deferred** - Gateway exists but not yet called by builder
3. **No provider health monitoring** - Fallback is reactive, not proactive
4. **No retry budget** - Retries count toward per-request token limit

## Next Steps (Wave 2)

1. **Plan 03-03: Sandboxed Validation Loop**
   - Wire gateway into builder for actual generation
   - Call `gateway.generate(purpose=Purpose.CODEGEN, ...)` from module builder
   - Use sandbox to validate generated adapter.py before install

2. **Plan 03-04: Installer with Rollback**
   - Use ArtifactIndex from Plan 01 for content-addressed installs
   - Atomic writes with rollback on validation failure

3. **Plan 03-05: Repair Loop**
   - Use `Purpose.REPAIR` lane for fixing validation errors
   - Feed validation errors back to gateway for repair generation

## Self-Check: PASSED

✅ **Created files exist:**
```bash
[ -f "shared/providers/github_models.py" ] && echo "FOUND"
# FOUND
[ -f "shared/providers/llm_gateway.py" ] && echo "FOUND"
# FOUND
[ -f "tests/unit/providers/test_github_models.py" ] && echo "FOUND"
# FOUND
[ -f "tests/unit/providers/test_llm_gateway.py" ] && echo "FOUND"
# FOUND
[ -f "tests/unit/providers/test_fallback_chain.py" ] && echo "FOUND"
# FOUND
```

✅ **Commits exist:**
```bash
git log --oneline --all | grep -q "77e46e5" && echo "FOUND: Task 1"
# FOUND: Task 1 (GitHub Models provider)
git log --oneline --all | grep -q "80c6bb7" && echo "FOUND: Task 2"
# FOUND: Task 2 (LLM Gateway)
git log --oneline --all | grep -q "3954eb3" && echo "FOUND: Task 3"
# FOUND: Task 3 (Fallback chain tests)
```

✅ **All claims verified** - files created, tests passing, commits recorded.
