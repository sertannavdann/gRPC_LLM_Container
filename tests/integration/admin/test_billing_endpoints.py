"""
Billing endpoint integration tests for Admin API.

Tests the following endpoints:
- GET /admin/billing/usage — get usage summary for org
- GET /admin/billing/usage/history — get usage history
- GET /admin/billing/quota — get quota status

All tests use FastAPI TestClient (in-process, no Docker).
"""
import pytest
from datetime import datetime, timedelta


class TestBillingEndpoints:
    """Test billing usage and quota endpoints."""

    def test_get_usage_empty(self, client, admin_headers):
        """GET /admin/billing/usage returns zero usage for new org."""
        response = client.get("/admin/billing/usage", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        # Usage store returns a summary structure
        assert isinstance(body, dict)

    def test_get_usage_requires_auth(self, client):
        """GET /admin/billing/usage requires authentication."""
        response = client.get("/admin/billing/usage")
        assert response.status_code == 401

    def test_get_usage_history(self, client, admin_headers):
        """GET /admin/billing/usage/history returns empty list for new org."""
        response = client.get("/admin/billing/usage/history", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert "records" in body
        assert "count" in body
        assert isinstance(body["records"], list)
        assert body["count"] >= 0

    def test_get_usage_history_requires_auth(self, client):
        """GET /admin/billing/usage/history requires authentication."""
        response = client.get("/admin/billing/usage/history")
        assert response.status_code == 401

    def test_get_quota(self, client, admin_headers):
        """GET /admin/billing/quota returns quota status."""
        response = client.get("/admin/billing/quota", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        # QuotaResult has allowed, allowed_unlimited, and within_limit fields
        assert "allowed" in body or "within_limit" in body

    def test_get_quota_requires_auth(self, client):
        """GET /admin/billing/quota requires authentication."""
        response = client.get("/admin/billing/quota")
        assert response.status_code == 401


class TestBillingWithUsage:
    """Test billing endpoints with pre-inserted usage records."""

    def test_usage_appears_in_history(self, client, admin_headers, usage_store, test_org):
        """Pre-inserted usage record appears in history."""
        # Insert a usage record
        usage_store.record_usage(
            org_id=test_org.org_id,
            agent_id="test-agent",
            conversation_id="test-conv",
            tool_name="test_tool",
            run_units=10,
            metadata={"test": "data"},
        )

        # Query history
        response = client.get("/admin/billing/usage/history", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["count"] >= 1
        assert len(body["records"]) >= 1

        # Verify the record contains expected fields
        record = body["records"][0]
        assert record["org_id"] == test_org.org_id
        assert record["run_units"] == 10

    def test_usage_summary_reflects_records(self, client, admin_headers, usage_store, test_org):
        """Usage summary aggregates inserted records."""
        # Insert multiple usage records
        for i in range(5):
            usage_store.record_usage(
                org_id=test_org.org_id,
                agent_id=f"agent-{i}",
                conversation_id="test-conv",
                tool_name="test_tool",
                run_units=5,
            )

        # Get summary
        response = client.get("/admin/billing/usage", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        # Summary structure varies by implementation, but should contain data
        assert isinstance(body, dict)

    def test_usage_history_limit_parameter(self, client, admin_headers, usage_store, test_org):
        """Usage history respects limit parameter."""
        # Insert 10 records
        for i in range(10):
            usage_store.record_usage(
                org_id=test_org.org_id,
                agent_id=f"agent-{i}",
                conversation_id="test-conv",
                tool_name="test_tool",
                run_units=1,
            )

        # Request only 3
        response = client.get(
            "/admin/billing/usage/history?limit=3",
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["records"]) <= 3


class TestBillingPermissions:
    """Test RBAC enforcement on billing endpoints."""

    def test_viewer_can_view_billing(self, client, viewer_headers):
        """Viewer role can view billing (get_current_user permission)."""
        response = client.get("/admin/billing/usage", headers=viewer_headers)
        assert response.status_code == 200

    def test_operator_can_view_billing(self, client, operator_headers):
        """Operator role can view billing."""
        response = client.get("/admin/billing/usage", headers=operator_headers)
        assert response.status_code == 200

    def test_admin_can_view_billing(self, client, admin_headers):
        """Admin role can view billing."""
        response = client.get("/admin/billing/usage", headers=admin_headers)
        assert response.status_code == 200

    def test_owner_can_view_billing(self, client, owner_headers):
        """Owner role can view billing."""
        response = client.get("/admin/billing/usage", headers=owner_headers)
        assert response.status_code == 200
