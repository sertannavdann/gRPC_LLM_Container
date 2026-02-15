"""
shared.auth — Authentication and authorization package for NEXUS.

Provides API key management, RBAC permission system, and auth models.
"""
from .api_keys import APIKeyStore
from .middleware import APIKeyAuthMiddleware, create_auth_middleware
from .models import APIKeyRecord, Organization, Role, User
from .rbac import Permission, get_current_user, has_permission, require_permission

__all__ = [
    "APIKeyAuthMiddleware",
    "APIKeyRecord",
    "APIKeyStore",
    "Organization",
    "Permission",
    "Role",
    "User",
    "create_auth_middleware",
    "get_current_user",
    "has_permission",
    "require_permission",
]
