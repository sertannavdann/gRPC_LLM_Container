"""
Real-client 429 integration test for RateLimitMiddleware (Plan 08-05, Task 2).

Builds a real admin API test app (via `create_test_admin_app()`) and adds the
REAL RateLimitMiddleware with `enabled=True` and a small burst, so this file
is the ONE place in this directory that exercises actual throttling
end-to-end. Every other file here must remain 429-free — see the
`_disable_inbound_rate_limiting` autouse fixture in `conftest.py`, which sets
`RATE_LIMIT_ENABLED=false` for the directory; this file overrides that with
`enabled=True` passed explicitly to the middleware constructor (Task 1).

Distinct from `tests/feature/test_rate_limit_429.py`, which tests OUTBOUND
provider 429 handling with mocks (RESEARCH Pitfall 1) — this file tests
INBOUND HTTP rate limiting with a real TestClient.

`tests/integration/conftest.py` applies an autouse Docker gate
(`test_environment`) to this whole directory that skips if the orchestrator
gRPC service isn't reachable on port 50054. This file never talks to that
service — it only builds an in-process FastAPI app — but the gate may still
skip it in CI without Docker, per the suite convention shared by every other
file in this directory.
"""
import pytest
from starlette.testclient import TestClient

from shared.auth.middleware import APIKeyAuthMiddleware
from shared.auth.rate_limit_middleware import RateLimitMiddleware

from integration.admin.conftest import create_test_admin_app


@pytest.fixture
def rate_limited_admin_app(
    config_manager,
    module_loader,
    module_registry,
    credential_store,
    api_key_store,
    usage_store,
    quota_manager,
    modules_dir,
    audit_log,
    audit_store,
):
    """Real admin test app with the REAL RateLimitMiddleware wired in.

    Uses a tiny burst so exhaustion is deterministic within a handful of
    requests, and `enabled=True` so the middleware throttles regardless of
    this directory's `RATE_LIMIT_ENABLED=false` autouse fixture.
    """
    app = create_test_admin_app()

    app.state.config_manager = config_manager
    app.state.module_loader = module_loader
    app.state.module_registry = module_registry
    app.state.credential_store = credential_store
    app.state.api_key_store = api_key_store
    app.state.usage_store = usage_store
    app.state.quota_manager = quota_manager
    app.state.modules_dir = modules_dir
    app.state.audit_log = audit_log
    app.state.audit_store = audit_store

    # Auth added first so RateLimitMiddleware (added second) becomes
    # OUTERMOST — same relative order as production's start_admin_server().
    app.add_middleware(
        APIKeyAuthMiddleware,
        api_key_store=api_key_store,
        public_paths=["/admin/health"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        rules={"/admin/modules": (0.01, 2), "/": (0.01, 2)},
        enabled=True,
    )

    return app


@pytest.fixture
def rate_limited_client(rate_limited_admin_app):
    return TestClient(rate_limited_admin_app)


class TestInboundRateLimit:
    def test_exhausting_budget_returns_429_with_retry_after(
        self, rate_limited_client, admin_headers
    ):
        """Exceeding burst on an admin path returns 429 + Retry-After."""
        responses = [
            rate_limited_client.get("/admin/modules", headers=admin_headers)
            for _ in range(3)
        ]
        statuses = [r.status_code for r in responses]
        assert 429 in statuses

        throttled = next(r for r in responses if r.status_code == 429)
        body = throttled.json()
        assert body["error"] == "rate_limit_exceeded"
        assert int(throttled.headers["Retry-After"]) >= 1

    def test_different_api_key_still_succeeds(
        self, rate_limited_client, admin_headers, operator_headers
    ):
        """A different X-API-Key gets an independent bucket."""
        for _ in range(3):
            rate_limited_client.get("/admin/modules", headers=admin_headers)

        # operator_headers mints a fresh key -> fresh, unexhausted bucket.
        resp = rate_limited_client.get("/admin/modules", headers=operator_headers)
        assert resp.status_code != 429

    def test_admin_health_never_throttled(self, rate_limited_client):
        """/admin/health is exempt from both auth and rate limiting."""
        for _ in range(10):
            resp = rate_limited_client.get("/admin/health")
            assert resp.status_code == 200
