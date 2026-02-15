"""
Auth Models — Pydantic models for authentication and authorization.

Defines Role enum, Organization, User, and APIKeyRecord models
used throughout the auth package.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    OWNER = "owner"


class Organization(BaseModel):
    org_id: str = Field(..., description="Unique organization identifier")
    name: str
    created_at: str
    plan: str = Field(default="free", description="Subscription plan")


class User(BaseModel):
    user_id: str
    org_id: str
    role: Role
    email: Optional[str] = None
    created_at: Optional[str] = None


class APIKeyRecord(BaseModel):
    key_id: str
    org_id: str
    role: Role
    created_at: str
    last_used: Optional[str] = None
    status: str = Field(default="active", description="active, rotation_pending, revoked")
