# Phase 01: Auth Boundary (Admin/Bridge) - Research

**Researched:** 2026-02-15
**Domain:** API Security, Multi-tenant Architecture, RBAC
**Confidence:** HIGH

## Summary

Phase 1 implements minimal authentication and authorization for the NEXUS platform's Admin API (port 8003) and Dashboard API (port 8001). The research confirms that the standard FastAPI + SQLite stack used throughout NEXUS is well-suited for API key authentication with RBAC. The phase builds on existing patterns in the codebase (SQLite stores in `module_registry.py` and `credentials.py`, FastAPI middleware in Admin API).

**Key findings:**
- FastAPI provides robust middleware and dependency injection for API key auth
- SHA-256 hashing is insufficient for password hashing but acceptable for API keys when combined with high-entropy generation using Python's `secrets` module
- Multi-key overlap strategy enables zero-downtime API key rotation
- SQLite with `org_id` scoping is proven for multi-tenant data isolation
- Permission decorator pattern using `Depends()` aligns with existing FastAPI patterns in the codebase

**Primary recommendation:** Use middleware for authentication (API key validation) + dependency injection for authorization (RBAC permission checks). Store API keys SHA-256 hashed in SQLite. Implement dual-key overlap for rotation. Scope all queries by `org_id` using a context manager pattern.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.109+ | HTTP API framework | Already used in `admin_api.py`, `dashboard_service/main.py` |
| Pydantic | 2.0+ | Data validation | Already used throughout (avoid `from __future__ import annotations`) |
| SQLite | 3.40+ | Persistent storage | Already used in `module_registry.py`, `credentials.py` |
| Python `secrets` | stdlib | Cryptographically strong random API keys | Standard library, high-entropy key generation |
| Python `hashlib` | stdlib | SHA-256 hashing | Standard library, sufficient for API key hashing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `cryptography` | 42.0+ | Fernet encryption (optional) | Already used in `credentials.py` for module credentials |
| `datetime` | stdlib | Timestamps for key rotation tracking | Standard library |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SHA-256 | bcrypt/Argon2 | Overkill for API keys (designed for passwords). SHA-256 + high-entropy `secrets` is sufficient. |
| SQLite | PostgreSQL RLS | PostgreSQL Row-Level Security offers database-enforced tenant isolation, but adds operational complexity. SQLite aligns with existing NEXUS architecture. |
| FastAPI middleware | Dependency-only auth | Middleware + dependency injection together provides cleaner separation: middleware authenticates (validates API key), dependencies authorize (check permissions). |

**Installation:**
```bash
# All dependencies already present in existing requirements.txt
# No new packages needed
```

## Architecture Patterns

### Recommended Project Structure
```
shared/auth/
├── __init__.py          # Export public API
├── api_keys.py          # APIKeyStore class (generate, hash, validate)
├── rbac.py              # Role enum, permission matrix, has_permission()
├── middleware.py        # FastAPI middleware for API key validation
├── models.py            # Pydantic models (Organization, User, Role)
└── context.py           # Request context manager for org_id injection

orchestrator/admin_api.py       # Wire middleware + RBAC decorators
dashboard_service/main.py       # Wire middleware + RBAC decorators
core/state.py                   # Add org_id field to AgentState
shared/modules/registry.py      # Add org_id scoping to queries
shared/modules/credentials.py   # Add org_id scoping to queries
```

### Pattern 1: Middleware-Based Authentication
**What:** FastAPI middleware intercepts every request, validates the `X-API-Key` header, and attaches the authenticated user to `request.state.user`.
**When to use:** All Admin API and Dashboard API endpoints (except public health checks).
**Example:**
```python
# Source: FastAPI middleware pattern + NEXUS codebase style
# shared/auth/middleware.py

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from .api_keys import APIKeyStore
from .models import User

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key_store: APIKeyStore):
        super().__init__(app)
        self.api_key_store = api_key_store

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health checks
        if request.url.path in ["/health", "/admin/health"]:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key:
            raise HTTPException(status_code=401, detail="Missing API key")

        user = self.api_key_store.validate_key(api_key)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Attach user to request state for downstream dependencies
        request.state.user = user
        request.state.org_id = user.org_id

        response = await call_next(request)
        return response
```

### Pattern 2: Dependency Injection for Authorization (RBAC)
**What:** Reusable FastAPI dependencies that extract the user from `request.state` and check permissions.
**When to use:** Endpoint-level permission enforcement.
**Example:**
```python
# Source: FastAPI RBAC pattern with Depends()
# shared/auth/rbac.py

from enum import Enum
from fastapi import Depends, HTTPException, Request
from .models import User, Role

class Permission(Enum):
    READ_CONFIG = "read_config"
    WRITE_CONFIG = "write_config"
    MANAGE_MODULES = "manage_modules"
    MANAGE_CREDENTIALS = "manage_credentials"
    ADMIN_ALL = "admin_all"

ROLE_PERMISSIONS = {
    Role.VIEWER: {Permission.READ_CONFIG},
    Role.OPERATOR: {Permission.READ_CONFIG, Permission.MANAGE_MODULES},
    Role.ADMIN: {Permission.READ_CONFIG, Permission.WRITE_CONFIG, Permission.MANAGE_MODULES},
    Role.OWNER: {Permission.READ_CONFIG, Permission.WRITE_CONFIG, Permission.MANAGE_MODULES, Permission.MANAGE_CREDENTIALS, Permission.ADMIN_ALL},
}

def get_current_user(request: Request) -> User:
    """Extract authenticated user from request state."""
    if not hasattr(request.state, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.state.user

def require_permission(permission: Permission):
    """Return a dependency that checks if user has required permission."""
    def permission_checker(user: User = Depends(get_current_user)) -> User:
        if permission not in ROLE_PERMISSIONS.get(user.role, set()):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: requires {permission.value}"
            )
        return user
    return permission_checker

# Usage in endpoints:
# @app.post("/admin/modules/{category}/{platform}/enable", dependencies=[Depends(require_permission(Permission.MANAGE_MODULES))])
```

### Pattern 3: Multi-Tenant Data Isolation with org_id Scoping
**What:** Every database query includes `org_id` filter. Use a context manager or base class method to enforce scoping.
**When to use:** All queries to `module_registry`, `credential_store`, `routing_config`.
**Example:**
```python
# Source: Multi-tenant SQLite pattern
# shared/modules/registry.py (modified)

class ModuleRegistry:
    def list_modules(self, org_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List modules scoped to organization."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM modules WHERE org_id = ? AND status = ? ORDER BY category, name",
                    (org_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM modules WHERE org_id = ? ORDER BY category, name",
                    (org_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_module(self, org_id: str, module_id: str) -> Optional[Dict[str, Any]]:
        """Get module scoped to organization."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM modules WHERE org_id = ? AND module_id = ?",
                (org_id, module_id),
            ).fetchone()
        return dict(row) if row else None
```

### Pattern 4: Zero-Downtime API Key Rotation (Dual-Key Overlap)
**What:** Support multiple valid keys per user/org. New key is created, consumers update, old key revoked after grace period.
**When to use:** Production deployments, key rotation events.
**Example:**
```python
# Source: API key rotation pattern
# shared/auth/api_keys.py

class APIKeyStore:
    def rotate_key(self, org_id: str, key_id: str) -> tuple[str, str]:
        """
        Rotate an API key using dual-key overlap strategy.

        Returns: (new_key_plaintext, new_key_id)

        Process:
        1. Generate new key
        2. Mark old key as "rotation_pending" (grace period)
        3. Return new key to client
        4. After grace period (e.g., 7 days), revoke old key
        """
        new_key = self.generate_key()
        new_key_id = self._store_key(org_id, new_key, status="active")

        # Mark old key for rotation
        with self._connect() as conn:
            conn.execute(
                "UPDATE api_keys SET status = 'rotation_pending', rotation_grace_until = ? WHERE org_id = ? AND key_id = ?",
                (datetime.utcnow() + timedelta(days=7), org_id, key_id),
            )

        return new_key, new_key_id

    def validate_key(self, key_plaintext: str) -> Optional[User]:
        """Validate key — accepts both active and rotation_pending keys."""
        key_hash = hashlib.sha256(key_plaintext.encode()).hexdigest()
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ? AND status IN ('active', 'rotation_pending')",
                (key_hash,),
            ).fetchone()

        if row is None:
            return None

        # Update last_used timestamp
        self._update_last_used(row["key_id"])

        return User(org_id=row["org_id"], role=Role(row["role"]), user_id=row["user_id"])
```

### Anti-Patterns to Avoid
- **Hardcoded permission checks in every endpoint:** Use dependency injection with `Depends(require_permission(...))` instead.
- **Storing plaintext API keys:** Always SHA-256 hash before storage.
- **Missing org_id in queries:** Every query MUST include `org_id` filter to prevent data leakage.
- **Single-key rotation:** Use dual-key overlap to avoid downtime during key rotation.
- **Ignoring last_used timestamps:** Track API key usage to detect stale/leaked keys.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Random key generation | `random.randint()`, `uuid.uuid4()` | `secrets.token_urlsafe(32)` | `secrets` provides cryptographically strong randomness. `random` is predictable. |
| Password hashing | SHA-256 for passwords | bcrypt/Argon2 | SHA-256 is too fast — vulnerable to brute force. Use KDFs for passwords (but SHA-256 is fine for high-entropy API keys). |
| SQL injection escaping | Manual string escaping | Parameterized queries (`?` placeholders) | Already used throughout NEXUS. Never concatenate SQL strings. |
| JWT token validation | Manual base64 decode + signature check | `python-jose` or `PyJWT` | Edge cases (timing attacks, algorithm confusion). Out of scope for Phase 1 but relevant for future OAuth. |
| Rate limiting | In-memory counters | `slowapi` or Redis-backed limiter | In-memory counters don't work across multiple orchestrator instances. Defer to Phase 2. |

**Key insight:** The NEXUS codebase already uses `secrets` for encryption keys (`credentials.py` line 45), SQLite with parameterized queries (`module_registry.py`), and Pydantic for validation. Phase 1 extends these patterns rather than introducing new dependencies.

## Common Pitfalls

### Pitfall 1: SQLite Concurrent Write Contention
**What goes wrong:** Multiple services (orchestrator + dashboard) writing to `api_keys.db` simultaneously cause "database is locked" errors.
**Why it happens:** SQLite locks the entire database during writes. Default timeout is 5 seconds.
**How to avoid:**
- Use WAL mode: `PRAGMA journal_mode=WAL;` (already used in production for `module_registry.db`)
- Increase busy timeout: `conn.execute("PRAGMA busy_timeout = 10000")`
- Minimize transaction duration: commit quickly, avoid long-running transactions
**Warning signs:** Intermittent 500 errors during key validation, "database is locked" in logs.

### Pitfall 2: Forgetting org_id Scoping in New Queries
**What goes wrong:** Adding a new feature (e.g., module search) that queries `module_registry` without `org_id` filter exposes all orgs' data.
**Why it happens:** Easy to forget when copy-pasting query templates.
**How to avoid:**
- Create base class methods that always inject `org_id`: `_scoped_query(org_id, sql, params)`
- Code review checklist: "Does this query filter by org_id?"
- Integration tests: Create two orgs, verify data isolation
**Warning signs:** Admin API returning data from wrong org_id in test environments.

### Pitfall 3: Middleware Ordering (CORS before Auth)
**What goes wrong:** If auth middleware runs before CORS middleware, preflight OPTIONS requests fail with 401.
**Why it happens:** OPTIONS requests don't include auth headers.
**How to avoid:**
- Order matters: `app.add_middleware(CORSMiddleware)` BEFORE `app.add_middleware(APIKeyAuthMiddleware)`
- Skip auth for OPTIONS requests in middleware: `if request.method == "OPTIONS": return await call_next(request)`
**Warning signs:** Browser shows CORS errors, OPTIONS requests return 401.

### Pitfall 4: API Key Enumeration Attacks
**What goes wrong:** Attacker tries millions of API keys, discovers valid ones by timing differences or different error messages.
**Why it happens:** Validation logic reveals whether key exists (fast reject) vs. invalid hash (slow reject).
**How to avoid:**
- Constant-time comparison: Always hash the input key and compare hashes, even if key doesn't exist
- Generic error message: Return same "Invalid API key" for missing and invalid keys
- Rate limiting: Defer to Phase 2, but critical for production
**Warning signs:** Logs show thousands of 401s from same IP.

### Pitfall 5: Missing last_used Tracking for Key Rotation Audits
**What goes wrong:** Can't determine if old keys are still in use before revoking during rotation.
**Why it happens:** Forgetting to update `last_used` timestamp on every validation.
**How to avoid:**
- Always update `last_used` in `validate_key()` method
- Admin API endpoint: `GET /admin/api-keys?stale_days=30` to list unused keys
- Grace period monitoring: Log warning if rotation_pending key used after expected cutover date
**Warning signs:** Service outages after key revocation because old key still in use.

## Code Examples

Verified patterns from official sources and NEXUS codebase:

### API Key Generation
```python
# Source: Python secrets module (stdlib)
import secrets
import hashlib

def generate_api_key() -> str:
    """Generate a cryptographically strong 32-byte API key."""
    return secrets.token_urlsafe(32)  # Returns 43-char base64 string

def hash_api_key(key: str) -> str:
    """Hash API key with SHA-256 for storage."""
    return hashlib.sha256(key.encode()).hexdigest()
```

### FastAPI Middleware Wiring
```python
# Source: FastAPI middleware pattern + NEXUS admin_api.py
# orchestrator/admin_api.py

from shared.auth.middleware import APIKeyAuthMiddleware
from shared.auth.api_keys import APIKeyStore

# Initialize API key store
_api_key_store = APIKeyStore(db_path="data/api_keys.db")

# Add middleware (AFTER CORSMiddleware)
_app.add_middleware(APIKeyAuthMiddleware, api_key_store=_api_key_store)
```

### Pydantic Models for Organizations and Users
```python
# Source: NEXUS codebase Pydantic patterns (avoid `from __future__ import annotations`)
# shared/auth/models.py

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional

class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    OWNER = "owner"

class Organization(BaseModel):
    org_id: str = Field(..., description="Unique organization identifier")
    name: str
    created_at: str
    plan: str = Field(default="free", description="Subscription plan (free, pro, enterprise)")

class User(BaseModel):
    user_id: str
    org_id: str
    role: Role
    email: Optional[str] = None
    created_at: str

class APIKeyRecord(BaseModel):
    key_id: str
    org_id: str
    role: Role
    created_at: str
    last_used: Optional[str] = None
    status: str = Field(default="active", description="active, rotation_pending, revoked")
```

### SQLite Schema for API Keys
```python
# Source: NEXUS module_registry.py pattern
# shared/auth/api_keys.py

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    key_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    user_id TEXT,
    created_at TEXT NOT NULL,
    last_used TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    rotation_grace_until TEXT,
    rate_limit INTEGER DEFAULT 1000,
    UNIQUE(key_hash)
)
"""

CREATE_ORGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS organizations (
    org_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    plan TEXT DEFAULT 'free'
)
"""

CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    email TEXT,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TEXT NOT NULL,
    FOREIGN KEY(org_id) REFERENCES organizations(org_id)
)
"""
```

### AgentState Extension with org_id
```python
# Source: core/state.py (modified)

class AgentState(TypedDict):
    """Agent workflow state with organization scoping."""

    # Existing fields...
    messages: Annotated[Sequence[BaseMessage], add_messages]
    tool_results: list[dict]
    router_recommendation: Optional[dict]
    next_action: Optional[Literal["llm", "tools", "validate", "end"]]
    error: Optional[str]
    retry_count: int
    conversation_id: str
    user_id: Optional[str]
    metadata: dict

    # NEW: Organization scoping
    org_id: Optional[str]  # Injected by auth middleware via orchestrator
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JWT for API authentication | API keys with SHA-256 hashing | 2024+ | Simpler for machine-to-machine auth, no token expiry complexity. JWT still preferred for user-facing OAuth flows. |
| PostgreSQL RLS for multi-tenancy | SQLite with app-level org_id scoping | NEXUS design | Aligns with existing NEXUS SQLite architecture. PostgreSQL RLS offers database-enforced isolation but requires PostgreSQL. |
| bcrypt for all secrets | bcrypt for passwords, SHA-256 for API keys | 2020+ | High-entropy API keys don't need slow KDFs. bcrypt remains standard for user passwords. |
| Single key per user | Dual-key overlap for rotation | 2022+ | Zero-downtime key rotation. Standard in production systems. |

**Deprecated/outdated:**
- **HTTP Basic Auth for APIs:** Replaced by API keys or OAuth2. Basic auth sends credentials on every request (no revocation without password change).
- **MD5 hashing:** Cryptographically broken. Always use SHA-256 minimum (or SHA-3 for new systems).
- **Global admin credentials:** Replaced by per-org, per-user API keys with RBAC.

## Open Questions

1. **Should we implement rate limiting in Phase 1?**
   - What we know: FastAPI has `slowapi` library. NEXUS doesn't have Redis.
   - What's unclear: Whether in-memory rate limiting (per-process) is sufficient for single orchestrator + dashboard deployment.
   - Recommendation: Defer to Phase 2. Add `rate_limit` column to `api_keys` table now, implement enforcement in Phase 2 with Redis or shared SQLite counter.

2. **Should API keys be scoped to specific modules/endpoints?**
   - What we know: RBAC roles provide coarse-grained permissions (viewer/operator/admin/owner).
   - What's unclear: Whether users need fine-grained scoping (e.g., "this key can only access weather adapter").
   - Recommendation: Start with role-based permissions. Add endpoint scoping in Phase 3 if needed (store allowed endpoints in `api_keys` table JSON column).

3. **How should bridge_service authenticate with orchestrator/dashboard?**
   - What we know: Bridge service proxies external requests. Currently no auth between internal services.
   - What's unclear: Whether internal service-to-service auth is required (vs. network isolation via Docker `rag_net`).
   - Recommendation: Phase 1 focuses on external API auth. Internal service auth deferred to Phase 2 (mTLS or shared secret).

## Sources

### Primary (HIGH confidence)
- Python `secrets` module documentation: https://docs.python.org/3/library/secrets.html
- Python `hashlib` SHA-256 documentation: https://docs.python.org/3/library/hashlib.html
- FastAPI Middleware documentation: https://fastapi.tiangolo.com/tutorial/middleware/
- FastAPI Security documentation: https://fastapi.tiangolo.com/tutorial/security/
- NEXUS codebase patterns: `shared/modules/registry.py`, `shared/modules/credentials.py`, `orchestrator/admin_api.py`

### Secondary (MEDIUM confidence)
- [FastAPI RBAC - Full Implementation Tutorial](https://www.permit.io/blog/fastapi-rbac-full-implementation-tutorial)
- [FastAPI/Python Code Sample: API Role-Based Access Control](https://developer.auth0.com/resources/code-samples/api/fastapi/basic-role-based-access-control)
- [How to Become Great at API Key Rotation: Best Practices and Tips](https://blog.gitguardian.com/api-key-rotation-best-practices/)
- [Zero-Downtime API Key Rotation Guide](https://oneuptime.com/blog/post/2026-01-30-api-key-rotation/view)
- [Implementing Multitenancy In A Crud Application Using Sqlite](https://peerdh.com/blogs/programming-insights/implementing-multitenancy-in-a-crud-application-using-sqlite)
- [Multi-tenancy - High Performance SQLite](https://highperformancesqlite.com/watch/multi-tenancy)

### Tertiary (LOW confidence)
- [GitHub - BrunoTanabe/fastapi-apikey-authentication](https://github.com/BrunoTanabe/fastapi-apikey-authentication) - Example implementation (not official)
- [FastAPI with API Key Authentication (Medium)](https://medium.com/@joerosborne/fastapi-with-api-key-authentication-f630c22ce851) - Community blog post

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in use or stdlib
- Architecture: HIGH - Patterns verified in NEXUS codebase and official docs
- Pitfalls: MEDIUM - Based on SQLite/FastAPI community experience, not NEXUS-specific testing

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (30 days - stable ecosystem)

## Ready for Planning

Research complete. Key architectural decisions:

1. **Authentication:** FastAPI middleware validates `X-API-Key` header, attaches user to `request.state`
2. **Authorization:** Dependency injection with `Depends(require_permission(...))` for RBAC
3. **Storage:** SQLite with SHA-256 hashed keys, org_id scoping on all queries
4. **Rotation:** Dual-key overlap strategy with grace period
5. **Integration:** Extend existing `module_registry.py` and `credentials.py` patterns

Planner can now create PLAN.md files with specific tasks for:
- `shared/auth/` package creation
- SQLite schema initialization
- Middleware wiring in `admin_api.py` and `dashboard_service/main.py`
- org_id propagation through `AgentState` and service layers
- RBAC permission matrix implementation
