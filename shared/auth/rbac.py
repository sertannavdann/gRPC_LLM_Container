"""
RBAC Permission System — role-based access control for NEXUS APIs.

Defines permissions, role-permission mapping, and FastAPI dependencies
for endpoint-level authorization.
"""
from enum import Enum

from fastapi import Depends, HTTPException, Request

from .models import Role, User


class Permission(str, Enum):
    READ_CONFIG = "read_config"
    WRITE_CONFIG = "write_config"
    MANAGE_MODULES = "manage_modules"
    MANAGE_CREDENTIALS = "manage_credentials"
    MANAGE_KEYS = "manage_keys"
    ADMIN_ALL = "admin_all"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {Permission.READ_CONFIG},
    Role.OPERATOR: {Permission.READ_CONFIG, Permission.MANAGE_MODULES},
    Role.ADMIN: {
        Permission.READ_CONFIG,
        Permission.WRITE_CONFIG,
        Permission.MANAGE_MODULES,
        Permission.MANAGE_KEYS,
    },
    Role.OWNER: set(Permission),
}


def has_permission(role: Role, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


def get_current_user(request: Request) -> User:
    """Extract authenticated user from request state (FastAPI dependency)."""
    if not hasattr(request.state, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.state.user


def require_permission(permission: Permission):
    """Return a FastAPI dependency that checks if the user has the required permission."""
    def permission_checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: requires {permission.value}",
            )
        return user
    return permission_checker
