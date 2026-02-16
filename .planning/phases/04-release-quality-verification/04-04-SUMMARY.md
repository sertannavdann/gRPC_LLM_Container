---
phase: 04-release-quality-verification
plan: 04
subsystem: ui-settings
tags:
  - provider-lock
  - connection-test
  - settings-ui
  - release-quality
dependency_graph:
  requires:
    - settings-api-baseline
    - provider-config
  provides:
    - provider-lock-metadata
    - connection-test-endpoint
    - lock-unlock-ui
  affects:
    - settings-ux
    - provider-selection
tech_stack:
  added:
    - TypeScript abstract classes for provider unlock logic
    - Next.js API route for connection testing
  patterns:
    - Base class + subclass pattern for extensibility
    - Factory pattern for provider handler lookup
    - Inline connection test result display
key_files:
  created:
    - ui_service/src/lib/provider-lock/base.ts
    - ui_service/src/lib/provider-lock/providers.ts
    - ui_service/src/app/api/settings/connection-test/route.ts
    - tests/integration/ui/test_settings_provider_lock.py
  modified:
    - ui_service/src/app/api/settings/route.ts
    - ui_service/src/app/settings/page.tsx
decisions:
  - title: "Base class abstraction for provider unlock logic"
    rationale: "Enables dashboard APIs to reuse same validation rules without duplication"
    alternatives: ["Inline lock logic in routes", "Shared utility functions"]
    chosen: "Abstract base class with provider-specific subclasses"
  - title: "Lock only when connection prerequisites missing"
    rationale: "User decision from plan - avoid locking all cloud providers by default"
    alternatives: ["Lock all cloud providers until explicitly unlocked", "No locking at all"]
    chosen: "Lock only when required fields (API key + base URL) are missing"
  - title: "Inline connection test results in Settings UI"
    rationale: "Immediate feedback without modal or navigation, keeps UX minimal"
    alternatives: ["Modal dialog for results", "Separate test page", "Toast notifications"]
    chosen: "Inline result display below provider card"
metrics:
  duration_seconds: 414
  duration_minutes: 6.9
  tasks_completed: 3
  files_created: 4
  files_modified: 2
  tests_added: 12
  commits: 3
  completed_date: "2026-02-16"
---

# Phase 04 Plan 04: Provider Lock/Unlock with Connection Testing Summary

**One-liner:** Reusable provider unlock class hierarchy with requirement-based locking, API-driven connection testing, and inline UI feedback.

---

## Objective Recap

Add release-quality provider lock/unlock behavior in Settings: only providers lacking full connection requirements are locked, unlock is API-driven, connection test results are shown to users, and lock logic is abstracted into a base class for reuse by dashboard APIs.

Purpose: Fixes current provider selection UX bugs while establishing a reusable validation architecture (base + subclass pattern) for future dashboard integration.

---

## What Was Built

### 1. Reusable Provider Lock/Unlock Architecture

**Base class contract** (`ui_service/src/lib/provider-lock/base.ts`):
- `ProviderUnlockBase` abstract class with:
  - `getRequiredFields(envConfig): string[]` - returns missing requirements
  - `isLocked(envConfig): boolean` - derived from missing requirements
  - `testConnection(payload): Promise<ConnectionTestResult>` - provider-specific probe
  - `toStatus(envConfig)` - returns `{ locked, missingRequirements, canTest }`

**Concrete implementations** (`ui_service/src/lib/provider-lock/providers.ts`):
- `LocalUnlock` - always unlocked, no-op health check
- `NvidiaUnlock` - requires `NIM_API_KEY` + `NIM_BASE_URL`, tests via `/models` endpoint
- `OpenAIUnlock` - requires `OPENAI_API_KEY`, tests via `/models` endpoint
- `AnthropicUnlock` - requires `ANTHROPIC_API_KEY`, tests via minimal message request
- `PerplexityUnlock` - requires `PERPLEXITY_API_KEY`, tests via chat completion
- `getProviderUnlockHandler(providerName)` - factory for dashboard reuse

**Connection test design:**
- Lightweight probes (list models or minimal chat request)
- 10-second timeout for fail-fast behavior
- Standardized output: `{ success: boolean, message: string, details?: Record<string, unknown> }`

### 2. Settings API Lock Metadata + Connection Test Endpoint

**GET /api/settings enhancement:**
- Added `providerLocks` field with per-provider metadata:
  ```json
  {
    "providerLocks": {
      "local": { "locked": false, "missingRequirements": [], "canTest": true },
      "nvidia": { "locked": true, "missingRequirements": ["NIM_API_KEY"], "canTest": false },
      ...
    }
  }
  ```
- Lock state derives from unlock handler classes via `getProviderUnlockHandler(provider).toStatus(envConfig)`

**POST /api/settings/connection-test:**
- Accepts `{ provider: string, overrides?: Record<string, string> }`
- Returns standardized `{ success, message, details }` output
- 400 for missing/invalid provider, 200 with structured result for valid provider
- Uses same unlock handler classes for consistency

### 3. Settings UI Lock/Unlock Flow

**Provider card enhancements:**
- Lock icon badge for locked providers
- Missing requirements displayed inline (e.g., "Missing: NIM_API_KEY")
- Unlock button on locked providers (triggers connection test)
- Disabled selection for locked providers

**Connection test workflow:**
- Unlock button → POST to `/api/settings/connection-test`
- Loading state during test (spinner + "Testing..." text)
- Result displayed inline below provider card:
  - Success: green background + check icon
  - Failure: red background + alert icon + actionable message
- Successful test updates lock state in component state without page reload

**Save behavior:**
- Save button disabled when locked provider is selected
- Button text changes to "Provider Locked" when disabled due to lock
- Selection remains stable after unlock

### 4. Integration Tests

**Test coverage** (`tests/integration/ui/test_settings_provider_lock.py`):
- GET /api/settings includes providerLocks field
- Lock metadata structure validation (locked/missingRequirements/canTest fields)
- Local provider always unlocked
- Cloud providers lock based on missing credentials
- POST /api/settings/connection-test standardized response shape
- Invalid provider input returns 400 with clear error
- Local provider connection test always succeeds
- All providers have lock metadata
- Lock state matches environment configuration
- Non-500 responses for all known providers

**12 tests passing** with actionable failure messages.

---

## Deviations from Plan

None - plan executed exactly as written.

---

## Verification Results

### Automated Tests

```bash
$ python -m pytest tests/integration/ui/test_settings_provider_lock.py -v
========================== 12 passed in 2.80s ===========================
```

All tests passed:
- Provider lock metadata structure validation
- Connection test endpoint standardized output
- Lock state based on environment configuration
- Invalid input handling with 400 errors
- Local provider always unlocked

### API Verification

```bash
$ python3 -c "import requests; r=requests.get('http://localhost:5001/api/settings'); print('providerLocks' in r.json())"
True

$ python3 -c "import requests; r=requests.post('http://localhost:5001/api/settings/connection-test', json={'provider':'nvidia'}); print(r.json())"
{'success': False, 'message': 'NIM_API_KEY is required', 'details': {'provider': 'nvidia', 'error': 'missing_api_key'}}
```

- GET /api/settings returns `providerLocks` field with lock metadata per provider
- POST /api/settings/connection-test returns structured output with success/message/details
- Lock state correctly reflects missing environment variables

### Manual UI Verification

Settings page behavior confirmed:
- Locked providers show lock icon badge + missing requirements
- Unlock button triggers connection test with loading state
- Test results appear inline with appropriate styling (green=success, red=failure)
- Save button disabled when locked provider selected
- Provider selection disabled for locked providers

---

## Key Technical Decisions

### 1. Requirement-Based Locking (Not Default-Lock All Cloud Providers)

**Decision:** Only lock providers when required connection prerequisites are missing (API key + base URL when applicable).

**Rationale:** User decision from plan - avoids unnecessarily locking providers that have credentials. Perplexity showed unlocked because `PERPLEXITY_API_KEY` was present in environment.

**Impact:** Better UX - users with existing keys see unlocked state immediately.

### 2. Base Class + Subclass Pattern for Extensibility

**Decision:** Implement unlock logic via abstract base class with provider-specific subclasses.

**Rationale:** Enables dashboard APIs to reuse same validation rules via `getProviderUnlockHandler(providerName)` factory without duplicating logic across routes.

**Impact:** Future dashboard integration can call same classes for consistent lock/unlock behavior.

### 3. Inline Test Results (Not Modal or Separate Page)

**Decision:** Display connection test results inline below provider card.

**Rationale:** Minimal UX scope per plan - no new pages/modals. Immediate feedback without navigation.

**Impact:** Faster user feedback loop, keeps settings page self-contained.

### 4. Lightweight Connection Probes

**Decision:** Use minimal API calls for testing (list models or smallest chat request).

**Rationale:** Fast fail-fast behavior - 10s timeout prevents long waits. Reduces API quota usage.

**Implementation:**
- NVIDIA/OpenAI: GET /models endpoint
- Anthropic: Minimal message with Claude Haiku (smallest/fastest model)
- Perplexity: Minimal chat completion with smallest model

---

## Success Criteria Met

- ✅ Requirement-based lock logic applies only to providers missing full connection prerequisites
- ✅ Unlock logic implemented via base class + subclasses and reusable for dashboard APIs
- ✅ Unlock button triggers API connection test and shows output to user
- ✅ Provider selection persistence remains stable after lock/unlock interactions
- ✅ GET /api/settings includes lock metadata per provider
- ✅ POST /api/settings/connection-test returns standardized output and actionable failures
- ✅ Manual UI verification confirms lock gating + unlock + persisted selection flow

---

## Artifacts Summary

### Files Created (4)
1. `ui_service/src/lib/provider-lock/base.ts` (72 lines) - ProviderUnlockBase abstract class
2. `ui_service/src/lib/provider-lock/providers.ts` (325 lines) - Concrete unlock handlers + factory
3. `ui_service/src/app/api/settings/connection-test/route.ts` (92 lines) - Connection test endpoint
4. `tests/integration/ui/test_settings_provider_lock.py` (227 lines) - Integration tests

### Files Modified (2)
1. `ui_service/src/app/api/settings/route.ts` - Added providerLocks metadata via unlock handlers
2. `ui_service/src/app/settings/page.tsx` - Lock/unlock UI + connection test workflow

### Commits (3)
1. `3b6715b` - feat(04-04): implement provider lock/unlock base class architecture
2. `88f4616` - feat(04-04): add lock/unlock UI workflow in settings
3. `8edfd05` - feat(04-04): add integration tests for provider lock and connection test

---

## Self-Check: PASSED

### Created Files Verification

```bash
$ [ -f "ui_service/src/lib/provider-lock/base.ts" ] && echo "FOUND: ui_service/src/lib/provider-lock/base.ts"
FOUND: ui_service/src/lib/provider-lock/base.ts

$ [ -f "ui_service/src/lib/provider-lock/providers.ts" ] && echo "FOUND: ui_service/src/lib/provider-lock/providers.ts"
FOUND: ui_service/src/lib/provider-lock/providers.ts

$ [ -f "ui_service/src/app/api/settings/connection-test/route.ts" ] && echo "FOUND: ui_service/src/app/api/settings/connection-test/route.ts"
FOUND: ui_service/src/app/api/settings/connection-test/route.ts

$ [ -f "tests/integration/ui/test_settings_provider_lock.py" ] && echo "FOUND: tests/integration/ui/test_settings_provider_lock.py"
FOUND: tests/integration/ui/test_settings_provider_lock.py
```

### Commit Verification

```bash
$ git log --oneline --all | grep -q "3b6715b" && echo "FOUND: 3b6715b"
FOUND: 3b6715b

$ git log --oneline --all | grep -q "88f4616" && echo "FOUND: 88f4616"
FOUND: 88f4616

$ git log --oneline --all | grep -q "8edfd05" && echo "FOUND: 8edfd05"
FOUND: 8edfd05
```

All artifacts verified. Self-check PASSED.

---

## Next Steps

1. **Dashboard Integration:** Use `getProviderUnlockHandler(provider)` in dashboard APIs to show same lock state
2. **Connection Test Caching:** Cache successful test results to avoid redundant API calls
3. **Provider-Specific Error Messages:** Enhance error messages with provider-specific troubleshooting links
4. **Test Coverage Expansion:** Add tests for connection test with API key overrides (testing before saving)
5. **Manual Testing Guide:** Document manual testing scenarios for QA (locked provider → unlock → select → save flow)

---

## Lessons Learned

1. **Base class pattern pays off immediately:** Same handler classes used in both settings route and connection-test route without duplication
2. **TypeScript path aliases work seamlessly:** `@/lib/provider-lock/*` imports compiled correctly in Next.js build
3. **Inline UI feedback > Modals:** Faster user feedback, less context switching, simpler implementation
4. **Integration tests caught structure issues early:** Test-first approach for API structure prevented UI integration issues
5. **Docker rebuild required for TypeScript changes:** Next.js production mode uses pre-built bundle, full rebuild needed for new modules
