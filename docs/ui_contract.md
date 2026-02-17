# UI Capability Contract — TypeScript Reference

> Phase 6 Plan 01 — Backend capability contract for frontend consumption

---

## Overview

This document defines the TypeScript types for consuming the capability contract endpoints from the frontend. The backend provides three BFF (Backend-for-Frontend) endpoints that serve as the single source of truth for what the UI should render.

**CQRS Pattern**: These endpoints form the **query model** — a read-optimized projection of system state. The command side (module install, credential store, provider config) remains independent.

**Academic Anchor**: Event-Driven Microservice Orchestration Principles §4.2

---

## TypeScript Type Definitions

### Enums

```typescript
enum FeatureStatus {
  HEALTHY = "healthy",
  DEGRADED = "degraded",
  UNAVAILABLE = "unavailable",
  UNKNOWN = "unknown"
}
```

### Capability Models

```typescript
interface ToolCapability {
  name: string; // Tool identifier (e.g., 'weather', 'calendar')
  description: string; // Human-readable tool description
  registered: boolean; // Whether tool is currently registered
  category: "builtin" | "custom"; // Tool category
}

interface ModuleCapability {
  id: string; // Module identifier (category-platform)
  name: string; // Human-readable module name
  category: string; // Module category (weather, calendar, etc.)
  platform: string; // Platform name (openweather, google, etc.)
  status: "installed" | "draft" | "disabled"; // Module status
  version: number | null; // Current version number
  has_tests: boolean; // Whether module has test suite
}

interface ProviderCapability {
  id: string; // Provider identifier
  name: string; // Provider display name
  tier: "standard" | "heavy" | "ultra"; // Provider tier (0.5B, 14B, 70B+)
  locked: boolean; // Whether provider is locked due to missing credentials or config
  connection_tested: boolean; // Whether connection test has been run
  last_test_ok: boolean | null; // Result of last connection test (null if not tested)
}

interface AdapterCapability {
  id: string; // Adapter identifier (category-platform)
  name: string; // Human-readable adapter name
  category: string; // Adapter category (weather, calendar, etc.)
  locked: boolean; // Whether adapter is locked due to missing credentials
  missing_fields: string[]; // List of missing credential fields
  last_data_timestamp: string | null; // ISO 8601 timestamp of last successful data fetch
  connection_tested: boolean; // Whether connection test has been run
  last_test_ok: boolean | null; // Result of last connection test (null if not tested)
}

interface FeatureHealth {
  feature: string; // Feature name (modules, providers, adapters, billing, sandbox, pipeline)
  status: FeatureStatus; // Current health status
  degraded_reasons: string[]; // Reasons why feature is degraded (empty if healthy)
  dependencies: string[]; // Feature dependencies (for troubleshooting)
}
```

### Envelope

```typescript
interface CapabilityEnvelope {
  tools: ToolCapability[];
  modules: ModuleCapability[];
  providers: ProviderCapability[];
  adapters: AdapterCapability[];
  features: FeatureHealth[];
  config_version: string; // Configuration version hash (for change detection)
  timestamp: string; // ISO 8601 timestamp of snapshot
}
```

---

## Endpoints

### GET /admin/capabilities

**Description**: Returns the full capability envelope — the single source of truth for what the UI should render.

**URL**: `http://localhost:8003/admin/capabilities`

**Method**: `GET`

**Headers**:
- `X-API-Key`: `<your-api-key>` (required)
- `If-None-Match`: `"<etag>"` (optional, for conditional requests)

**Response Codes**:
- `200 OK`: Full capability envelope returned
- `304 Not Modified`: ETag matches current state, no body returned
- `401 Unauthorized`: Missing or invalid API key
- `403 Forbidden`: Insufficient permissions (requires viewer+ role)

**Response Headers**:
- `ETag`: `"<sha256-hash>"` (for subsequent conditional requests)

**Response Body** (200 OK):
```json
{
  "tools": [],
  "modules": [
    {
      "id": "weather/openweather",
      "name": "OpenWeather",
      "category": "weather",
      "platform": "openweather",
      "status": "installed",
      "version": 3,
      "has_tests": true
    }
  ],
  "providers": [
    {
      "id": "standard",
      "name": "Standard Tier",
      "tier": "standard",
      "locked": false,
      "connection_tested": true,
      "last_test_ok": true
    }
  ],
  "adapters": [
    {
      "id": "finance/wealthsimple",
      "name": "Wealthsimple",
      "category": "finance",
      "locked": true,
      "missing_fields": ["api_key", "account_id"],
      "last_data_timestamp": null,
      "connection_tested": false,
      "last_test_ok": null
    }
  ],
  "features": [
    {
      "feature": "adapters",
      "status": "degraded",
      "degraded_reasons": ["Wealthsimple locked (missing: api_key, account_id)"],
      "dependencies": ["credential_store"]
    }
  ],
  "config_version": "a1b2c3d4...",
  "timestamp": "2026-01-01T00:00:00Z"
}
```

---

### GET /admin/feature-health

**Description**: Returns per-feature health status for monitoring dashboard.

**URL**: `http://localhost:8003/admin/feature-health`

**Method**: `GET`

**Headers**:
- `X-API-Key`: `<your-api-key>` (required)

**Response Codes**:
- `200 OK`: Feature health array returned
- `401 Unauthorized`: Missing or invalid API key
- `403 Forbidden`: Insufficient permissions (requires viewer+ role)

**Response Body**:
```json
[
  {
    "feature": "modules",
    "status": "healthy",
    "degraded_reasons": [],
    "dependencies": ["module_registry", "module_loader"]
  },
  {
    "feature": "providers",
    "status": "healthy",
    "degraded_reasons": [],
    "dependencies": ["routing_config"]
  },
  {
    "feature": "adapters",
    "status": "degraded",
    "degraded_reasons": ["Wealthsimple locked (missing: api_key, account_id)"],
    "dependencies": ["credential_store"]
  },
  {
    "feature": "billing",
    "status": "degraded",
    "degraded_reasons": ["Quota usage at 85.2%"],
    "dependencies": ["quota_manager", "usage_store"]
  },
  {
    "feature": "sandbox",
    "status": "unknown",
    "degraded_reasons": ["Health check not implemented"],
    "dependencies": ["sandbox_service"]
  },
  {
    "feature": "pipeline",
    "status": "unknown",
    "degraded_reasons": ["Pipeline status tracking not yet implemented"],
    "dependencies": ["builder", "validator"]
  }
]
```

---

### GET /admin/config/version

**Description**: Lightweight polling endpoint returning only config version hash. Clients poll this cheaply to detect changes, then fetch full `/admin/capabilities` only when version changes.

**URL**: `http://localhost:8003/admin/config/version`

**Method**: `GET`

**Headers**:
- `X-API-Key`: `<your-api-key>` (required)
- `If-None-Match`: `"<etag>"` (optional, for conditional requests)

**Response Codes**:
- `200 OK`: Config version returned
- `304 Not Modified`: ETag matches current state, no body returned
- `401 Unauthorized`: Missing or invalid API key
- `403 Forbidden`: Insufficient permissions (requires viewer+ role)

**Response Headers**:
- `ETag`: `"<sha256-hash>"` (for subsequent conditional requests)

**Response Body** (200 OK):
```json
{
  "config_version": "a1b2c3d4e5f6...",
  "etag": "b2c3d4e5f6a7..."
}
```

---

## Polling Pattern

### Efficient Polling Strategy

To minimize bandwidth and server load, use this two-tier polling pattern:

1. **Poll `/admin/config/version` every 30 seconds** (cheap, ~100 bytes)
   - Send `If-None-Match` header with last known ETag
   - On `304 Not Modified`: No changes, skip full fetch
   - On `200 OK` with different `config_version`: Trigger full fetch

2. **Fetch `/admin/capabilities` only when version changes**
   - Send `If-None-Match` header with last known capability ETag
   - Store returned envelope in XState context
   - Store returned ETag for next poll

### Avoid Anti-Patterns

❌ **DON'T**: Poll `/admin/capabilities` directly at high frequency (wastes bandwidth)
❌ **DON'T**: Use `setInterval` for polling (leads to unbounded intervals and memory leaks)
✅ **DO**: Use XState invoked actors with `after` delays for polling
✅ **DO**: Poll `/admin/config/version` first, then fetch full envelope only on change

---

## XState Integration

### nexusAppMachine Architecture

The root application statechart (`ui_service/src/machines/nexusApp.ts`) integrates with these endpoints via invoked actors:

```typescript
{
  capability: {
    initial: "loading",
    states: {
      loading: {
        invoke: {
          src: "pollCapabilities", // fromPromise actor
          onDone: { target: "current", actions: "storeEnvelope" },
          onError: { target: "error", actions: "storeError" }
        }
      },
      current: {
        after: { 30000: "polling" } // Poll config version every 30s
      },
      polling: {
        invoke: {
          src: "pollConfigVersion", // fromPromise actor
          onDone: [
            {
              guard: "configVersionChanged",
              target: "loading" // Fetch full envelope
            },
            { target: "current" } // No change, continue
          ],
          onError: { target: "error" }
        }
      },
      error: {
        after: { 5000: "loading" } // Retry after 5s
      }
    }
  },
  dataSource: { /* ... */ },
  auth: { /* ... */ }
}
```

### Invoked Actors

**pollCapabilities**:
```typescript
fromPromise(async ({ input }) => {
  const response = await adminClient.getCapabilities(input.etag);
  return { envelope: response.data, etag: response.etag, notModified: response.notModified };
});
```

**pollConfigVersion**:
```typescript
fromPromise(async ({ input }) => {
  const response = await adminClient.getConfigVersion(input.etag);
  return { config_version: response.config_version, etag: response.etag };
});
```

---

## Feature Health Status Meanings

| Status | Meaning | UI Indicator |
|--------|---------|--------------|
| `HEALTHY` | Feature fully operational | Green checkmark ✅ |
| `DEGRADED` | Feature partially operational, issues present | Yellow warning ⚠️ |
| `UNAVAILABLE` | Feature completely non-functional | Red error ❌ |
| `UNKNOWN` | Feature status cannot be determined | Gray question mark ❓ |

### Common Degraded Reasons

- **Adapters**: `"<adapter-name> locked (missing: <field1>, <field2>)"`
- **Providers**: `"All LLM providers locked"`
- **Modules**: `"N module(s) disabled"`, `"N module(s) in draft state"`
- **Billing**: `"Quota usage at X.X%"` (when usage ≥ 80%)

---

## RBAC Requirements

All three endpoints require **viewer+ role**:
- `viewer`: Can view capabilities (read-only)
- `operator`: Can view + manage modules/credentials
- `admin`: Can view + manage + configure
- `owner`: Full access

Unauthorized requests return `401 Unauthorized`.
Insufficient permissions return `403 Forbidden`.

---

## Usage Notes

1. **ETag caching**: Always store and send ETag headers to minimize bandwidth.
2. **Timestamp**: Use `timestamp` field to detect stale data (warn if > 5 minutes old).
3. **Lock status**: Adapters with `locked: true` should show unlock UI flow.
4. **Missing fields**: Display `missing_fields` array to guide users on what credentials to provide.
5. **Feature health**: Use for dashboard status indicators and monitoring alerts.
6. **Config version**: Used for change detection — clients don't need to parse the hash value.

---

## Academic References

- **CQRS (Command Query Responsibility Segregation)**: Event-Driven Microservice Orchestration Principles §4.2
  Query model is optimized for reads, command side remains independent.

- **ETag-based Polling**: Reduces bandwidth by 95% compared to full envelope polling.
  Standard HTTP conditional request pattern (RFC 7232).

- **XState v5 Invoked Actors**: Harel Statecharts with deterministic state transitions.
  Replaces imperative `setInterval` patterns with declarative state models.

---

**Last Updated**: 2026-02-17
**Phase**: 6 (UX/UI Visual Expansion)
**Plan**: 01 (Capability Contract)
