---
phase: 01-auth-boundary
plan: 01
status: completed
completed_at: 2026-02-15
---

# Phase 01.01 Summary: Auth Models, API Key Store & RBAC

## What Was Built

Created the `shared/auth/` package with three modules providing the foundation for all authentication and authorization in NEXUS.

### Files Created

| File | Purpose | Key Exports |
|------|---------|-------------|
| `shared/auth/__init__.py` | Package public API | All public symbols |
| `shared/auth/models.py` | Pydantic data models | `Role`, `Organization`, `User`, `APIKeyRecord` |
| `shared/auth/api_keys.py` | SQLite-backed key store | `APIKeyStore` |
| `shared/auth/rbac.py` | Permission system | `Permission`, `ROLE_PERMISSIONS`, `has_permission`, `require_permission`, `get_current_user` |

### Capabilities

**API Key Store (`APIKeyStore`):**
- Key generation with `secrets.token_urlsafe(32)` (cryptographically strong)
- SHA-256 hashed storage (plaintext never persisted)
- Key validation returns `User` with org_id and role
- Dual-key rotation with configurable grace period
- Key revocation and listing per organization
- Organization and user CRUD
- SQLite with WAL mode and parameterized queries

**RBAC Permission Matrix:**
- `viewer`: read_config
- `operator`: read_config, manage_modules
- `admin`: read_config, write_config, manage_modules, manage_keys
- `owner`: all permissions (read_config, write_config, manage_modules, manage_credentials, manage_keys, admin_all)

**FastAPI Dependencies:**
- `get_current_user(request)` — extracts user from `request.state.user`
- `require_permission(permission)` — returns dependency that enforces RBAC, raises 401/403

## Verification Results

- Models import and instantiate correctly
- API key round-trip: generate -> validate -> User with correct role/org_id
- Key rotation: both old and new keys valid during grace period
- Key revocation: revoked keys return None on validation
- Invalid keys return None
- RBAC matrix: all permission checks match spec (viewer < operator < admin < owner)
- Package-level imports resolve all public symbols

## Dependencies for Next Plans

- **Plan 01-02 (Middleware):** Imports `APIKeyStore` and `User` to validate requests and attach user to `request.state`
- **Plan 01-03 (Multi-tenant):** Uses `User.org_id` for data isolation scoping
