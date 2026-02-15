"""
Integration tests for billing endpoints with auth and org scoping.
"""

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from shared.auth.api_keys import APIKeyStore
from shared.auth.middleware import APIKeyAuthMiddleware
from shared.auth.models import Role, User
from shared.auth.rbac import get_current_user
from shared.billing import QuotaManager, UsageStore


@pytest.fixture
def auth_store(tmp_path):
    return APIKeyStore(db_path=str(tmp_path / "auth_billing.db"))


@pytest.fixture
def usage_store(tmp_path):
    return UsageStore(db_path=str(tmp_path / "usage_billing.db"))


@pytest.fixture
def quota_manager(usage_store, auth_store):
    return QuotaManager(usage_store=usage_store, api_key_store=auth_store)


@pytest.fixture
def app_with_billing(auth_store, usage_store, quota_manager):
    app = FastAPI()

    @app.get("/admin/billing/usage")
    def billing_usage(period: str | None = None, user: User = Depends(get_current_user)):
        return usage_store.get_usage_summary(user.org_id, period=period)

    @app.get("/admin/billing/usage/history")
    def billing_history(
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        user: User = Depends(get_current_user),
    ):
        records = usage_store.get_usage_history(
            user.org_id,
            start_date=start_date,
            end_date=end_date,
            limit=min(limit, 1000),
        )
        return {"records": records, "count": len(records)}

    @app.get("/admin/billing/quota")
    def billing_quota(user: User = Depends(get_current_user)):
        result = quota_manager.check_quota(user.org_id)
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if hasattr(result, "dict"):
            return result.dict()
        raise HTTPException(500, "Invalid quota result")

    app.add_middleware(
        APIKeyAuthMiddleware,
        api_key_store=auth_store,
        public_paths=[],
    )

    return app


@pytest.fixture
def client(app_with_billing):
    return TestClient(app_with_billing)


@pytest.fixture
def seeded_orgs(auth_store, usage_store):
    auth_store.create_organization("org-a", "Org A", plan="free")
    auth_store.create_organization("org-b", "Org B", plan="free")

    key_a, _ = auth_store.create_key("org-a", Role.ADMIN.value)
    key_b, _ = auth_store.create_key("org-b", Role.ADMIN.value)

    usage_store.record("org-a", "weather_query", 1.2, tier="standard", user_id="user-a")
    usage_store.record("org-a", "build_module", 2.5, tier="heavy", user_id="user-a")
    usage_store.record("org-b", "weather_query", 0.7, tier="standard", user_id="user-b")

    return {"org_a_key": key_a, "org_b_key": key_b}


def test_billing_usage_endpoint(client, seeded_orgs):
    response = client.get(
        "/admin/billing/usage",
        headers={"X-API-Key": seeded_orgs["org_a_key"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["record_count"] == 2
    assert body["total_run_units"] == pytest.approx(3.7, abs=0.01)


def test_billing_quota_endpoint(client, seeded_orgs):
    response = client.get(
        "/admin/billing/quota",
        headers={"X-API-Key": seeded_orgs["org_a_key"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["plan"] == "free"
    assert body["remaining"] == pytest.approx(96.3, abs=0.1)


def test_billing_history_endpoint(client, seeded_orgs):
    response = client.get(
        "/admin/billing/usage/history?limit=1",
        headers={"X-API-Key": seeded_orgs["org_a_key"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert len(body["records"]) == 1


def test_billing_requires_auth(client):
    response = client.get("/admin/billing/usage")
    assert response.status_code == 401


def test_billing_org_isolation(client, seeded_orgs):
    response_a = client.get(
        "/admin/billing/usage",
        headers={"X-API-Key": seeded_orgs["org_a_key"]},
    )
    response_b = client.get(
        "/admin/billing/usage",
        headers={"X-API-Key": seeded_orgs["org_b_key"]},
    )

    assert response_a.status_code == 200
    assert response_b.status_code == 200

    total_a = response_a.json()["total_run_units"]
    total_b = response_b.json()["total_run_units"]

    assert total_a == pytest.approx(3.7, abs=0.01)
    assert total_b == pytest.approx(0.7, abs=0.01)


def test_quota_enforcement_blocks_request(client, auth_store, usage_store):
    auth_store.create_organization("org-limit", "Org Limit", plan="free")
    key, _ = auth_store.create_key("org-limit", Role.ADMIN.value)

    for _ in range(100):
        usage_store.record("org-limit", "test_tool", 1.0)

    response = client.get(
        "/admin/billing/quota",
        headers={"X-API-Key": key},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["remaining"] == 0.0
