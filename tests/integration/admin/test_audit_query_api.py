"""
Audit query API integration tests (REQ-012, Phase 07-03 Task 1).

Covers GET /admin/audit-logs (filtered query + pagination), GET
/admin/audit-logs/export (streaming CSV with an injection guard), and GET
/admin/audit-logs/verify (hash-chain verification) — all gated by the new
READ_AUDIT permission (admin/owner only, org-scoped unless OWNER).

All tests use FastAPI TestClient (in-process, no Docker) via the shared
create_test_admin_app() factory. Like other tests in this directory, the
suite is gated by the parent tests/integration/conftest.py autouse
`test_environment` fixture, which requires the orchestrator gRPC service to
be reachable on port 50054 (skips otherwise — see test_module_crud.py for
the identical, pre-existing pattern). Run with
`--confcutdir=tests/integration/admin` to bypass the Docker gate locally.
"""
import csv
import io
import sqlite3

import pytest

from shared.auth.models import Role
from shared.auth.rbac import Permission, has_permission


def _record(audit_store, **overrides):
    """Record one audit event with sane defaults, returning its id."""
    defaults = dict(
        org_id="test-org",
        actor_id="tester",
        action="module_enabled",
        resource_type="module",
        resource_id="weather/openweather",
        before_state=None,
        after_state={"enabled": True},
        ip_address="127.0.0.1",
        details=None,
    )
    defaults.update(overrides)
    return audit_store.record(**defaults)


class TestReadAuditPermission:
    """Permission.READ_AUDIT matrix (unit-level, mirrors endpoint RBAC below)."""

    def test_admin_has_read_audit(self):
        assert has_permission(Role.ADMIN, Permission.READ_AUDIT)

    def test_owner_has_read_audit(self):
        assert has_permission(Role.OWNER, Permission.READ_AUDIT)

    def test_viewer_lacks_read_audit(self):
        assert not has_permission(Role.VIEWER, Permission.READ_AUDIT)

    def test_operator_lacks_read_audit(self):
        assert not has_permission(Role.OPERATOR, Permission.READ_AUDIT)


class TestAuditLogsRBAC:
    """viewer/operator -> 403; admin/owner -> 200, across all three endpoints."""

    ENDPOINTS = [
        "/admin/audit-logs",
        "/admin/audit-logs/export",
        "/admin/audit-logs/verify",
    ]

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_viewer_forbidden(self, client, viewer_headers, path):
        response = client.get(path, headers=viewer_headers)
        assert response.status_code == 403

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_operator_forbidden(self, client, operator_headers, path):
        response = client.get(path, headers=operator_headers)
        assert response.status_code == 403

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_admin_allowed(self, client, admin_headers, path):
        response = client.get(path, headers=admin_headers)
        assert response.status_code == 200

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_owner_allowed(self, client, owner_headers, path):
        response = client.get(path, headers=owner_headers)
        assert response.status_code == 200


class TestQueryAuditLogs:
    def test_returns_events_ordered_id_desc(self, client, admin_headers, audit_store):
        ids = [_record(audit_store, action=f"action_{i}") for i in range(3)]
        response = client.get("/admin/audit-logs", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        returned_ids = [e["id"] for e in body["events"]]
        assert returned_ids == sorted(ids, reverse=True)

    def test_filters_by_action(self, client, admin_headers, audit_store):
        _record(audit_store, action="module_enabled")
        _record(audit_store, action="module_disabled")
        response = client.get(
            "/admin/audit-logs", params={"action": "module_disabled"}, headers=admin_headers
        )
        body = response.json()
        assert body["count"] == 1
        assert body["events"][0]["action"] == "module_disabled"

    def test_filters_by_actor_and_resource_type(self, client, admin_headers, audit_store):
        _record(audit_store, actor_id="alice", resource_type="module")
        _record(audit_store, actor_id="bob", resource_type="routing_config")
        response = client.get(
            "/admin/audit-logs",
            params={"actor_id": "alice", "resource_type": "module"},
            headers=admin_headers,
        )
        body = response.json()
        assert body["count"] == 1
        assert body["events"][0]["actor_id"] == "alice"

    def test_pagination_totals(self, client, admin_headers, audit_store):
        for i in range(5):
            _record(audit_store, action=f"paged_{i}")
        response = client.get(
            "/admin/audit-logs", params={"limit": 2, "offset": 0}, headers=admin_headers
        )
        body = response.json()
        assert len(body["events"]) == 2
        assert body["limit"] == 2
        assert body["offset"] == 0
        assert body["total"] >= 5
        assert body["count"] == 2

    def test_limit_capped_at_1000(self, client, admin_headers, audit_store):
        response = client.get(
            "/admin/audit-logs", params={"limit": 5000}, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["limit"] == 1000


class TestOrgScoping:
    def test_admin_cannot_see_other_org_events(self, client, admin_headers, audit_store):
        _record(audit_store, org_id="test-org", action="own_org_event")
        _record(audit_store, org_id="org-b", action="other_org_event")

        response = client.get("/admin/audit-logs", headers=admin_headers)
        body = response.json()
        actions = {e["action"] for e in body["events"]}
        assert "own_org_event" in actions
        assert "other_org_event" not in actions

    def test_owner_may_scope_to_other_org_via_param(self, client, owner_headers, audit_store):
        _record(audit_store, org_id="test-org", action="mine")
        _record(audit_store, org_id="org-b", action="theirs")

        response = client.get(
            "/admin/audit-logs", params={"org_id": "org-b"}, headers=owner_headers
        )
        body = response.json()
        actions = {e["action"] for e in body["events"]}
        assert actions == {"theirs"}

    def test_owner_without_org_param_sees_all_orgs(self, client, owner_headers, audit_store):
        _record(audit_store, org_id="test-org", action="mine")
        _record(audit_store, org_id="org-b", action="theirs")

        response = client.get("/admin/audit-logs", headers=owner_headers)
        body = response.json()
        actions = {e["action"] for e in body["events"]}
        assert actions == {"mine", "theirs"}


class TestExportCsv:
    def test_header_row_and_columns(self, client, admin_headers, audit_store):
        _record(audit_store)
        response = client.get("/admin/audit-logs/export", headers=admin_headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        assert rows[0] == [
            "id", "timestamp", "org_id", "actor_id", "action", "resource_type",
            "resource_id", "ip_address", "before_state", "after_state",
            "details", "prev_hash", "row_hash",
        ]
        assert len(rows) == 2  # header + 1 event

    def test_content_disposition_attachment(self, client, admin_headers, audit_store):
        _record(audit_store)
        response = client.get("/admin/audit-logs/export", headers=admin_headers)
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "audit_events_" in disposition
        assert disposition.endswith('.csv"')

    def test_injection_guarded_cell_gets_leading_apostrophe(self, client, admin_headers, audit_store):
        _record(audit_store, action="=cmd|' /C calc'!A1")
        response = client.get("/admin/audit-logs/export", headers=admin_headers)
        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        action_col = rows[0].index("action")
        data_row = rows[1]
        assert data_row[action_col].startswith("'=")

    def test_export_respects_org_scoping(self, client, admin_headers, audit_store):
        _record(audit_store, org_id="test-org", action="mine")
        _record(audit_store, org_id="org-b", action="theirs")
        response = client.get("/admin/audit-logs/export", headers=admin_headers)
        assert "theirs" not in response.text
        assert "mine" in response.text


class TestVerifyChain:
    def test_valid_chain(self, client, admin_headers, audit_store):
        _record(audit_store)
        _record(audit_store)
        response = client.get("/admin/audit-logs/verify", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["checked"] == 2
        assert body["first_invalid_id"] is None

    def test_tampered_chain_reports_first_invalid_id(
        self, client, admin_headers, audit_store, tmp_databases
    ):
        for _ in range(3):
            _record(audit_store)

        conn = sqlite3.connect(tmp_databases["audit"])
        conn.execute("DROP TRIGGER audit_events_no_update")
        conn.execute("UPDATE audit_events SET action = 'tampered' WHERE id = 2")
        conn.commit()
        conn.execute(
            """
            CREATE TRIGGER audit_events_no_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events is append-only');
            END
            """
        )
        conn.commit()
        conn.close()

        response = client.get("/admin/audit-logs/verify", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is False
        assert body["first_invalid_id"] == 2
        assert body["reason"]

    def test_verify_accepts_start_end_id_params(self, client, admin_headers, audit_store):
        for _ in range(5):
            _record(audit_store)
        response = client.get(
            "/admin/audit-logs/verify",
            params={"start_id": 2, "end_id": 4},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["checked"] == 3
        assert body["valid"] is True
