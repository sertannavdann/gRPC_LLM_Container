"""
Auth Middleware — FastAPI middleware for API key authentication.

Intercepts requests, validates X-API-Key header via APIKeyStore,
and attaches the authenticated User to request.state.
"""
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .api_keys import APIKeyStore

logger = logging.getLogger(__name__)

DEFAULT_PUBLIC_PATHS = [
    "/health",
    "/admin/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/metrics",
]


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates X-API-Key header on every request.

    Skips auth for OPTIONS (CORS preflight) and configurable public paths.
    On success, attaches User and org_id to request.state.
    """

    def __init__(
        self,
        app,
        api_key_store: APIKeyStore,
        public_paths: Optional[list[str]] = None,
    ):
        super().__init__(app)
        self.api_key_store = api_key_store
        self.public_paths = public_paths or DEFAULT_PUBLIC_PATHS

    async def dispatch(self, request: Request, call_next):
        # Skip auth for CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip auth for public paths
        path = request.url.path
        for public in self.public_paths:
            if path == public or path.startswith(public + "/"):
                return await call_next(request)

        # Extract API key from header
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API key"},
            )

        # Validate key
        user = self.api_key_store.validate_key(api_key)
        if user is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"},
            )

        # Attach user to request state for downstream dependencies
        request.state.user = user
        request.state.org_id = user.org_id

        return await call_next(request)


def create_auth_middleware(
    app,
    db_path: str = "data/api_keys.db",
    public_paths: Optional[list[str]] = None,
) -> APIKeyStore:
    """
    Create APIKeyStore and add auth middleware to app.

    Returns the store instance for bootstrapping/seeding keys.
    """
    store = APIKeyStore(db_path=db_path)
    app.add_middleware(
        APIKeyAuthMiddleware,
        api_key_store=store,
        public_paths=public_paths,
    )
    return store
