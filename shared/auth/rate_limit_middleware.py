"""
Rate Limit Middleware — FastAPI middleware for inbound token-bucket rate limiting.

Wraps the existing shared.utils.rate_limiter.TokenBucketRateLimiter (used today
only for OUTBOUND provider throttling) so every inbound HTTP endpoint on both
FastAPI services (Admin API :8003, Dashboard API :8001) is protected with a
429 + Retry-After response (REQ-020).

Mirrors shared.auth.middleware.APIKeyAuthMiddleware's structure and error-
response style so the two middlewares are easy to read side by side.
"""
import hashlib
import logging
import os
from typing import Dict, List, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from shared.utils.rate_limiter import get_rate_limiter_registry

logger = logging.getLogger(__name__)

DEFAULT_EXEMPT_PATHS = ["/health", "/admin/health", "/metrics"]

# path prefix -> (requests_per_second, burst). Rule selection picks the
# LONGEST matching prefix; "/" is the catch-all default for everything else.
DEFAULT_RATE_LIMIT_RULES: Dict[str, Tuple[float, int]] = {
    "/admin/bootstrap": (0.2, 3),
    "/admin/modules": (5.0, 20),
    "/admin": (10.0, 40),
    "/": (20.0, 60),
}

RATE_LIMIT_ENABLED_ENV = "RATE_LIMIT_ENABLED"


def _fingerprint(identity: str) -> str:
    """Short, non-reversible fingerprint of an identity for safe logging.

    NEVER log or echo the raw API key / IP directly (T-08-22).
    """
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that throttles inbound requests using the in-repo token-bucket
    limiter, keyed on the X-API-Key header (falling back to client IP so
    unauthenticated endpoints are protected too).

    Must run OUTSIDE (i.e. added AFTER, per Starlette's reverse add order)
    APIKeyAuthMiddleware so invalid-key brute force is throttled before
    authentication ever runs. Never reads the auth-attached user from
    request state — it is not populated yet when this middleware is
    outermost.
    """

    def __init__(
        self,
        app,
        rules: Optional[Dict[str, Tuple[float, int]]] = None,
        default_rate: Optional[float] = None,
        default_burst: Optional[int] = None,
        exempt_paths: Optional[List[str]] = None,
        enabled: Optional[bool] = None,
    ):
        super().__init__(app)

        # Start from the shipped defaults, then let a caller-supplied `rules`
        # dict add/override individual prefixes — this is how limits stay
        # "configurable per endpoint prefix without code changes" (no need
        # to repeat the whole default set to add one narrow rule).
        merged_rules: Dict[str, Tuple[float, int]] = dict(DEFAULT_RATE_LIMIT_RULES)
        caller_overrode_root = bool(rules and "/" in rules)
        if rules:
            merged_rules.update(rules)

        if not caller_overrode_root:
            env_rps = os.getenv("RATE_LIMIT_RPS")
            env_burst = os.getenv("RATE_LIMIT_BURST")
            root_rate, root_burst = merged_rules["/"]
            if default_rate is not None:
                root_rate = default_rate
            elif env_rps is not None:
                root_rate = float(env_rps)
            if default_burst is not None:
                root_burst = default_burst
            elif env_burst is not None:
                root_burst = int(env_burst)
            merged_rules["/"] = (root_rate, root_burst)

        self.rules = merged_rules
        self.exempt_paths = exempt_paths or DEFAULT_EXEMPT_PATHS

        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv(RATE_LIMIT_ENABLED_ENV, "true").strip().lower()
            not in ("0", "false", "no")
        )
        if not self.enabled:
            logger.warning(
                "Inbound rate limiting DISABLED via %s — this must only happen in tests",
                RATE_LIMIT_ENABLED_ENV,
            )

    def _resolve_rule(self, path: str) -> Tuple[str, float, int]:
        """Return (prefix, rate, burst) for the LONGEST matching rule prefix."""
        best_prefix = "/"
        for prefix in self.rules:
            if prefix == "/":
                continue
            if path == prefix or path.startswith(prefix + "/"):
                if len(prefix) > len(best_prefix):
                    best_prefix = prefix
        rate, burst = self.rules.get(best_prefix, self.rules["/"])
        return best_prefix, rate, burst

    async def dispatch(self, request: Request, call_next):
        # Enable switch is checked FIRST — no bucket is even created when
        # disabled (dispatch() short-circuits before any registry access).
        if not self.enabled:
            return await call_next(request)

        # Skip throttling for CORS preflight (same convention as auth middleware).
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        for exempt in self.exempt_paths:
            if path == exempt or path.startswith(exempt + "/"):
                return await call_next(request)

        # Never read the auth-attached user from request state — it is not
        # populated yet when this middleware is outermost (RESEARCH Pitfall
        # 3). Read the raw header instead.
        identity = request.headers.get("X-API-Key") or (
            request.client.host if request.client else "anonymous"
        )
        rule_prefix, rule_rate, rule_burst = self._resolve_rule(path)
        bucket_key = f"http:{rule_prefix}:{identity}"

        registry = get_rate_limiter_registry()
        # Register explicitly on first use so the registry's PROVIDER
        # defaults (DEFAULT_LIMITS) never silently apply to an HTTP bucket.
        # Re-registering an EXISTING bucket would reset its token count, so
        # only register when this bucket_key has never been seen before.
        if bucket_key not in registry._limiters:
            registry.register(bucket_key, rate=rule_rate, burst=rule_burst)
        limiter = registry.get(bucket_key)

        if not await limiter.acquire():
            retry_after = limiter.retry_after()
            logger.warning(
                "Rate limit exceeded: path=%s rule=%s identity_fp=%s",
                path,
                rule_prefix,
                _fingerprint(identity),
            )
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "retry_after": retry_after},
                headers={
                    "Retry-After": str(max(1, int(retry_after) + 1)),
                    # This middleware sits OUTSIDE CORSMiddleware on the
                    # admin API, so the 429 needs its own CORS header.
                    "Access-Control-Allow-Origin": os.getenv(
                        "CORS_ORIGINS", "*"
                    ).split(",")[0],
                },
            )

        return await call_next(request)
