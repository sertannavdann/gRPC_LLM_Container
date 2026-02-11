# Known Issues & Technical Debt

**Last Updated**: February 2026

This document tracks current limitations, technical debt, and planned improvements.

---

## High Priority

### 1. Module Builder Not Implemented (Track A4)

**Issue**: `build_module` tool is stubbed but not functional.

**Impact**: Cannot generate modules from natural language descriptions yet.

**Workaround**: Manually create modules using templates.

**Fix**: Implement LLM-driven code generation (Q2 2026).

**Tracking**: Track A4 milestone in ROADMAP.md

---

### 2. No Approval Gates for Module Installation

**Issue**: Modules can be enabled without user review of code or credentials.

**Impact**: Security risk - malicious modules could be installed without oversight.

**Workaround**: Manually review module code before enabling.

**Fix**: Implement approval gates UI (Track C3, Q2 2026).

**Tracking**: Track C3 milestone in ROADMAP.md

---

### 3. Admin API Lacks Automated Tests

**Issue**: Admin API v2 CRUD operations have no integration tests.

**Impact**: Regressions may go undetected during refactoring.

**Workaround**: Manual testing via curl or Postman.

**Fix**: Add pytest integration tests (Q2 2026).

**Test Plan**:
- `tests/integration/test_admin_api.py`
- Test module enable/disable/reload/uninstall
- Test credential store/retrieve
- Test config hot-reload

---

### 4. Dashboard Service Violates SRP

**Issue**: Dashboard service handles too many concerns:
- Context aggregation
- Adapter management
- Bank service logic
- Pipeline SSE streaming
- Module listing

**Impact**: Hard to maintain, test, and scale.

**Workaround**: None (architectural issue).

**Fix**: Refactor into microservices:
- Context service (aggregation only)
- Adapter service (adapter registry + enablement)
- Finance service (bank logic)
- Stream service (SSE endpoints)

**Tracking**: Planned for Q3 2026 refactor.

---

### 5. Finance Categorizer Uses Hardcoded Regex (OCP Violation)

**Issue**: `shared/adapters/finance/categorizer.py` has 100+ hardcoded regex patterns.

**Impact**: Cannot extend categories without modifying source code (violates Open-Closed Principle).

**Workaround**: Edit categorizer.py and redeploy.

**Fix**: Move categories to config file or database:
```json
{
  "categories": [
    {
      "name": "Food & Dining",
      "patterns": ["starbucks", "mcdonald", "restaurant"]
    }
  ]
}
```

**Tracking**: Q3 2026 refactor.

---

## Medium Priority

### 6. No E2E Tests for Pipeline SSE Reconnection

**Issue**: Pipeline UI SSE reconnection logic is not tested.

**Impact**: Cannot verify behavior when dashboard service restarts.

**Workaround**: Manual testing (stop dashboard, observe UI).

**Fix**: Add Playwright E2E tests (Q2 2026).

**Test Plan**:
- Test SSE initial connection
- Test reconnection after dashboard restart
- Test error handling on SSE failure

---

### 7. No Module Versioning or Rollback

**Issue**: Modules have version in manifest but no rollback mechanism.

**Impact**: Cannot revert to previous version if new version breaks.

**Workaround**: Manually backup modules/ directory.

**Fix**: Implement module versioning:
- Store multiple versions in registry
- Add `POST /admin/modules/{cat}/{plat}/rollback?version={v}` endpoint

**Tracking**: Q3 2026.

---

### 8. Credential Validation Logic Scattered

**Issue**: Credential validation happens in multiple places:
- Adapter `fetch_raw()` methods
- Dashboard service `/adapters` endpoint
- Admin API credential check endpoint

**Impact**: Inconsistent validation, hard to maintain.

**Workaround**: None (architectural issue).

**Fix**: Centralize validation in `CredentialStore.validate()` method.

**Tracking**: Q3 2026 refactor.

---

### 9. No Rate Limiting on API Endpoints

**Issue**: Admin API and Dashboard API have no rate limiting.

**Impact**: Vulnerable to DoS attacks.

**Workaround**: Use reverse proxy (nginx) with rate limiting.

**Fix**: Implement Redis-backed rate limiting (Q3 2026).

**Example**:
```python
from fastapi_limiter import FastAPILimiter

@app.get("/context")
@limiter.limit("10/minute")
async def get_context():
    ...
```

---

### 10. Missing API Versioning

**Issue**: All endpoints are implicitly v1, no versioning scheme.

**Impact**: Cannot introduce breaking changes without affecting clients.

**Workaround**: Be careful with breaking changes.

**Fix**: Implement URL-based versioning:
- `/v1/admin/modules` (current)
- `/v2/admin/modules` (future breaking changes)

**Tracking**: Q3 2026.

---

## Low Priority

### 11. No Caching for Expensive Adapter Calls

**Issue**: Adapters fetch from external APIs every time (no TTL cache).

**Impact**: Higher latency, more API costs, potential rate limit issues.

**Workaround**: Implement manual caching in adapters.

**Fix**: Redis cache with TTL:
```python
@cache(ttl=300)  # 5 minutes
async def fetch_weather():
    ...
```

**Tracking**: Q4 2026.

---

### 12. Logs Not Centralized (No ELK Stack)

**Issue**: Logs in individual containers, hard to search across services.

**Impact**: Difficult debugging for multi-service issues.

**Workaround**: Use `make logs-core` to view multiple services.

**Fix**: Deploy ELK stack (Elasticsearch, Logstash, Kibana) (Q4 2026).

---

### 13. No Automated Dependency Updates

**Issue**: Python packages and npm packages need manual updates.

**Impact**: Security vulnerabilities, missing features.

**Workaround**: Manually run `pip-audit` and `npm audit`.

**Fix**: Enable Dependabot or Renovate Bot (Q2 2026).

---

### 14. No Health Check for gRPC Services

**Issue**: gRPC services (llm, chroma, sandbox) lack HTTP health endpoints.

**Impact**: Harder to monitor in Prometheus/Grafana.

**Workaround**: Use gRPC health check protocol (grpc.health.v1).

**Fix**: Add HTTP health endpoints alongside gRPC (Q3 2026).

**Example**:
```python
# In llm_service
@app.get("/health")
async def health():
    return {"status": "healthy"}
```

---

### 15. UI Settings Lack Validation

**Issue**: Settings page allows invalid configurations (empty strings, negative numbers).

**Impact**: User errors can break system.

**Workaround**: Manually validate before saving.

**Fix**: Add Zod validation schemas in UI (Q2 2026).

**Example**:
```typescript
const settingsSchema = z.object({
  api_key: z.string().min(10),
  temperature: z.number().min(0).max(2)
});
```

---

## Workarounds in Production

### Temporary Fixes Currently in Use

1. **Module Validation**: Manually test modules before enabling (until Track A4 sandbox validation).
2. **Credential Rotation**: Manual process via Admin API (until automatic expiration warnings).
3. **Service Monitoring**: Manual checks via curl (until comprehensive health dashboard).
4. **Log Analysis**: Manual grep through log files (until ELK stack).

---

## Fixed Issues (Archive)

### Fixed in February 2026

- ✅ **Context formatters in wrong service**: Moved to dashboard service (SRP fix).
- ✅ **No container metrics**: Added cAdvisor monitoring.
- ✅ **No module status visualization**: Added Pipeline UI.
- ✅ **Hardcoded model configurations**: Moved to `routing_config.json`.

### Fixed in January 2026

- ✅ **Credentials in plain text**: Added Fernet encryption.
- ✅ **No module persistence**: Added SQLite registry.
- ✅ **Supervisor-worker overhead**: Replaced with unified orchestrator.

---

## Reporting New Issues

**GitHub Issues**: [repository URL]

**Issue Template**:
```markdown
### Description
[What's the issue?]

### Expected Behavior
[What should happen?]

### Actual Behavior
[What actually happens?]

### Steps to Reproduce
1. ...
2. ...

### Impact
[High/Medium/Low]

### Workaround
[If any]
```

---

## See Also

- [ROADMAP.md](./ROADMAP.md) - Feature roadmap and milestones
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [OPERATIONS.md](./OPERATIONS.md) - Troubleshooting guide
