"""
Unit tests for shared.auth.rate_limit_middleware — RateLimitMiddleware.

Real TestClient over a minimal FastAPI app, exercising the middleware
directly. No Docker, no live services — always runs.
"""
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from shared.auth.rate_limit_middleware import (
    DEFAULT_RATE_LIMIT_RULES,
    RATE_LIMIT_ENABLED_ENV,
    RateLimitMiddleware,
)
from shared.utils.rate_limiter import get_rate_limiter_registry


@pytest.fixture(autouse=True)
def _clear_rate_limiter_registry():
    """The rate limiter registry is a process-wide singleton (RESEARCH
    interface note) — clear it before AND after each test so buckets never
    leak between tests in this module or across the pytest process.
    """
    registry = get_rate_limiter_registry()
    registry._limiters.clear()
    yield
    registry._limiters.clear()


def _build_app(**middleware_kwargs) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/admin/modules/x")
    def admin_modules_x():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/admin/health")
    def admin_health():
        return {"ok": True}

    @app.get("/metrics")
    def metrics():
        return {"ok": True}

    @app.get("/admin/audit-logs")
    def admin_audit_logs():
        return {"ok": True}

    app.add_middleware(RateLimitMiddleware, **middleware_kwargs)
    return app


class TestDefaultRules:
    def test_default_rules_seeded(self):
        assert "/admin/bootstrap" in DEFAULT_RATE_LIMIT_RULES
        assert "/admin/modules" in DEFAULT_RATE_LIMIT_RULES
        assert "/admin" in DEFAULT_RATE_LIMIT_RULES
        assert "/" in DEFAULT_RATE_LIMIT_RULES


class TestBasicThrottling:
    def test_requests_within_budget_pass_through(self):
        app = _build_app(rules={"/": (100.0, 3)}, enabled=True)
        client = TestClient(app)
        for _ in range(3):
            resp = client.get("/ping", headers={"X-API-Key": "key-a"})
            assert resp.status_code == 200

    def test_first_request_beyond_budget_returns_429_with_retry_after(self):
        app = _build_app(rules={"/": (0.01, 1)}, enabled=True)
        client = TestClient(app)
        first = client.get("/ping", headers={"X-API-Key": "key-b"})
        assert first.status_code == 200

        second = client.get("/ping", headers={"X-API-Key": "key-b"})
        assert second.status_code == 429
        body = second.json()
        assert body["error"] == "rate_limit_exceeded"
        assert isinstance(body["retry_after"], float)
        assert int(second.headers["Retry-After"]) >= 1

    def test_distinct_api_keys_get_independent_buckets(self):
        app = _build_app(rules={"/": (0.01, 1)}, enabled=True)
        client = TestClient(app)

        r1 = client.get("/ping", headers={"X-API-Key": "key-c1"})
        assert r1.status_code == 200
        r1_exhausted = client.get("/ping", headers={"X-API-Key": "key-c1"})
        assert r1_exhausted.status_code == 429

        r2 = client.get("/ping", headers={"X-API-Key": "key-c2"})
        assert r2.status_code == 200

    def test_no_api_key_buckets_by_client_ip(self):
        app = _build_app(rules={"/": (0.01, 1)}, enabled=True)
        client = TestClient(app)

        first = client.get("/ping")
        assert first.status_code == 200
        second = client.get("/ping")
        assert second.status_code == 429

    def test_options_requests_never_throttled(self):
        app = _build_app(rules={"/": (0.01, 1)}, enabled=True)
        client = TestClient(app)

        # Exhaust the bucket first.
        client.get("/ping", headers={"X-API-Key": "key-opt"})
        client.get("/ping", headers={"X-API-Key": "key-opt"})

        for _ in range(5):
            resp = client.options("/ping", headers={"X-API-Key": "key-opt"})
            assert resp.status_code != 429

    def test_per_endpoint_rule_overrides_default(self):
        app = _build_app(
            rules={"/": (100.0, 100), "/admin/modules": (0.01, 1)},
            enabled=True,
        )
        client = TestClient(app)

        # Default rule is generous — /ping should never throttle.
        for _ in range(5):
            resp = client.get("/ping", headers={"X-API-Key": "key-rule"})
            assert resp.status_code == 200

        # /admin/modules has a strict override (burst=1).
        first = client.get("/admin/modules/x", headers={"X-API-Key": "key-rule"})
        assert first.status_code == 200
        second = client.get("/admin/modules/x", headers={"X-API-Key": "key-rule"})
        assert second.status_code == 429

    def test_exempt_paths_never_throttled(self):
        app = _build_app(rules={"/": (0.01, 1)}, enabled=True)
        client = TestClient(app)

        for path in ("/health", "/admin/health", "/metrics"):
            for _ in range(5):
                resp = client.get(path, headers={"X-API-Key": "key-exempt"})
                assert resp.status_code != 429


class TestEnableSwitch:
    def test_env_var_false_disables_throttling(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENABLED_ENV, "false")
        app = _build_app(rules={"/": (0.01, 1)})
        client = TestClient(app)

        for _ in range(10):
            resp = client.get("/ping", headers={"X-API-Key": "key-disabled"})
            assert resp.status_code == 200

    def test_default_enabled_when_env_var_absent(self, monkeypatch):
        monkeypatch.delenv(RATE_LIMIT_ENABLED_ENV, raising=False)
        app = _build_app(rules={"/": (0.01, 1)})
        client = TestClient(app)

        first = client.get("/ping", headers={"X-API-Key": "key-default-on"})
        assert first.status_code == 200
        second = client.get("/ping", headers={"X-API-Key": "key-default-on"})
        assert second.status_code == 429

    def test_explicit_enabled_true_overrides_env_var_false(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENABLED_ENV, "false")
        app = _build_app(rules={"/": (0.01, 1)}, enabled=True)
        client = TestClient(app)

        first = client.get("/ping", headers={"X-API-Key": "key-override"})
        assert first.status_code == 200
        second = client.get("/ping", headers={"X-API-Key": "key-override"})
        assert second.status_code == 429

    def test_disabled_logs_one_warning_at_construction(self, monkeypatch, caplog):
        monkeypatch.setenv(RATE_LIMIT_ENABLED_ENV, "false")
        with caplog.at_level(
            "WARNING", logger="shared.auth.rate_limit_middleware"
        ):
            _build_app(rules={"/": (0.01, 1)})

        warnings = [r for r in caplog.records if "DISABLED" in r.message]
        assert len(warnings) == 1
