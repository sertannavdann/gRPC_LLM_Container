"""
Module approval gate integration tests for Admin API (Phase 8 plan 08-01).

Tests the following endpoints:
- POST /admin/modules/{category}/{platform}/approve — admin+ only (D-16/D-17)
- POST /admin/modules/{category}/{platform}/reject — admin+ only (D-09/D-10)
- GET /admin/modules/{category}/{platform}/review — operator+ (D-05 review payload)
- GET /admin/modules/{category}/{platform}/audit — operator+ (build attempt records)

All tests use FastAPI TestClient (in-process, no Docker) via the shared
create_test_admin_app() factory. Like other tests in this directory, the
suite is gated by the parent tests/integration/conftest.py autouse
`test_environment` fixture, which requires the orchestrator gRPC service to
be reachable on port 50054 (skips otherwise — see test_module_crud.py for
the identical, pre-existing pattern).
"""
import json

import pytest

from shared.modules.manifest import ModuleManifest, ModuleStatus

from integration.admin.conftest import ADMIN_TEST_USER_ID


def _create_module(modules_dir, module_id: str, status: str) -> ModuleManifest:
    """Create a minimal module manifest + adapter files on disk."""
    category, platform = module_id.split("/")
    module_dir = modules_dir / category / platform
    module_dir.mkdir(parents=True, exist_ok=True)

    manifest = ModuleManifest(
        name=platform,
        category=category,
        platform=platform,
        status=status,
        display_name=platform.title(),
        requires_api_key=True,
        auth_type="api_key",
        api_key_instructions="Provide your API key.",
    )
    manifest.save(modules_dir)

    adapter_code = '''
from shared.adapters.base import BaseAdapter, register_adapter

@register_adapter
class DemoAdapter(BaseAdapter):
    def fetch_raw(self):
        return {"value": 1}

    def transform(self, raw):
        return raw

    def get_schema(self):
        return {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
            },
        }
'''
    (module_dir / "adapter.py").write_text(adapter_code)
    (module_dir / "test_adapter.py").write_text("def test_a(): assert True\n")

    return manifest


class TestApprovalGateRBAC:
    """RBAC enforcement on approve/reject mutation endpoints (D-17)."""

    def test_approve_requires_admin_viewer_forbidden(self, client, viewer_headers, modules_dir):
        _create_module(modules_dir, "test/rbac_viewer", ModuleStatus.VALIDATED.value)
        response = client.post(
            "/admin/modules/test/rbac_viewer/approve", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_approve_requires_admin_operator_forbidden(self, client, operator_headers, modules_dir):
        _create_module(modules_dir, "test/rbac_operator", ModuleStatus.VALIDATED.value)
        response = client.post(
            "/admin/modules/test/rbac_operator/approve", headers=operator_headers
        )
        assert response.status_code == 403

    def test_approve_admin_allowed(self, client, admin_headers, modules_dir):
        _create_module(modules_dir, "test/rbac_admin", ModuleStatus.VALIDATED.value)
        response = client.post(
            "/admin/modules/test/rbac_admin/approve", headers=admin_headers
        )
        assert response.status_code == 200

    def test_reject_requires_admin_viewer_forbidden(self, client, viewer_headers, modules_dir):
        _create_module(modules_dir, "test/rbac_reject_viewer", ModuleStatus.VALIDATED.value)
        response = client.post(
            "/admin/modules/test/rbac_reject_viewer/reject",
            headers=viewer_headers,
            json={"feedback": None},
        )
        assert response.status_code == 403

    def test_reject_requires_admin_operator_forbidden(self, client, operator_headers, modules_dir):
        _create_module(modules_dir, "test/rbac_reject_operator", ModuleStatus.VALIDATED.value)
        response = client.post(
            "/admin/modules/test/rbac_reject_operator/reject",
            headers=operator_headers,
            json={"feedback": None},
        )
        assert response.status_code == 403

    def test_reject_admin_allowed(self, client, admin_headers, modules_dir):
        _create_module(modules_dir, "test/rbac_reject_admin", ModuleStatus.VALIDATED.value)
        response = client.post(
            "/admin/modules/test/rbac_reject_admin/reject",
            headers=admin_headers,
            json={"feedback": None},
        )
        assert response.status_code == 200


class TestApproveModule:
    """POST /admin/modules/{category}/{platform}/approve (D-16)."""

    def test_approve_validated_module_transitions_to_approved(
        self, client, admin_headers, modules_dir
    ):
        _create_module(modules_dir, "test/approve_ok", ModuleStatus.VALIDATED.value)

        response = client.post(
            "/admin/modules/test/approve_ok/approve", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["new_status"] == "approved"

        manifest = ModuleManifest.load(modules_dir / "test" / "approve_ok" / "manifest.json")
        assert manifest.status == ModuleStatus.APPROVED.value

    def test_approve_non_validated_module_rejected(self, client, admin_headers, modules_dir):
        _create_module(modules_dir, "test/approve_pending", ModuleStatus.PENDING.value)

        response = client.post(
            "/admin/modules/test/approve_pending/approve", headers=admin_headers
        )

        assert response.status_code == 400

    def test_approve_records_audit_entry_with_actor_and_hash(
        self, client, admin_headers, modules_dir, audit_log
    ):
        """D-19: every approve decision is recorded with actor, timestamp, and bundle hash."""
        _create_module(modules_dir, "test/approve_audit", ModuleStatus.VALIDATED.value)

        response = client.post(
            "/admin/modules/test/approve_audit/approve", headers=admin_headers
        )
        assert response.status_code == 200

        events = audit_log.get_events(module_id="test/approve_audit", action="module_approved")
        assert len(events) >= 1
        last_event = events[-1]
        assert last_event.action == "module_approved"
        assert last_event.actor
        assert "bundle_sha256" in last_event.details
        assert "timestamp" in last_event.details

        # WR-02: actor must be the individual admin's user_id, NOT the
        # tenant org_id — org context is preserved separately in details.
        assert last_event.actor == ADMIN_TEST_USER_ID
        assert last_event.actor != "test-org"
        assert last_event.details.get("org_id") == "test-org"


class TestRejectModule:
    """POST /admin/modules/{category}/{platform}/reject (D-09/D-10)."""

    def test_reject_without_feedback_is_terminal(self, client, admin_headers, modules_dir):
        _create_module(modules_dir, "test/reject_terminal", ModuleStatus.VALIDATED.value)

        response = client.post(
            "/admin/modules/test/reject_terminal/reject",
            headers=admin_headers,
            json={"feedback": None},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["new_status"] == "failed"

        manifest = ModuleManifest.load(
            modules_dir / "test" / "reject_terminal" / "manifest.json"
        )
        assert manifest.status == ModuleStatus.FAILED.value

        # D-10: terminal rejection queues artifacts for GC
        gc_marker = modules_dir / "test" / "reject_terminal" / ".gc_pending"
        assert gc_marker.exists()
        marker_data = json.loads(gc_marker.read_text())
        assert marker_data["module_id"] == "test/reject_terminal"

    def test_reject_with_feedback_returns_to_validating(self, client, admin_headers, modules_dir):
        _create_module(modules_dir, "test/reject_feedback", ModuleStatus.VALIDATED.value)

        response = client.post(
            "/admin/modules/test/reject_feedback/reject",
            headers=admin_headers,
            json={"feedback": "Missing error handling on the fetch path."},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["new_status"] == "validating"

        manifest = ModuleManifest.load(
            modules_dir / "test" / "reject_feedback" / "manifest.json"
        )
        assert manifest.status == ModuleStatus.VALIDATING.value

        # Non-terminal rejection must NOT queue for GC
        gc_marker = modules_dir / "test" / "reject_feedback" / ".gc_pending"
        assert not gc_marker.exists()

    def test_reject_records_audit_entry_with_terminal_flag(
        self, client, admin_headers, modules_dir, audit_log
    ):
        """D-19: reject decisions are recorded with actor, timestamp, hash, terminal flag."""
        _create_module(modules_dir, "test/reject_audit", ModuleStatus.VALIDATED.value)

        response = client.post(
            "/admin/modules/test/reject_audit/reject",
            headers=admin_headers,
            json={"feedback": None},
        )
        assert response.status_code == 200

        events = audit_log.get_events(module_id="test/reject_audit", action="module_rejected")
        assert len(events) >= 1
        last_event = events[-1]
        assert last_event.details["terminal"] is True
        assert "bundle_sha256" in last_event.details


class TestReviewAndAuditReadEndpoints:
    """GET .../review and GET .../audit — operator+ read access (D-05/D-06)."""

    def test_review_requires_operator_viewer_forbidden(self, client, viewer_headers, modules_dir):
        _create_module(modules_dir, "test/review_viewer", ModuleStatus.VALIDATED.value)
        response = client.get(
            "/admin/modules/test/review_viewer/review", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_review_operator_allowed(self, client, operator_headers, modules_dir):
        _create_module(modules_dir, "test/review_operator", ModuleStatus.VALIDATED.value)

        response = client.get(
            "/admin/modules/test/review_operator/review", headers=operator_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["module_id"] == "test/review_operator"
        assert body["status"] == ModuleStatus.VALIDATED.value
        assert "validation_results" in body
        assert "walkthrough" in body
        assert body["credentials"]["requires_api_key"] is True
        assert "blueprint" in body

    def test_review_not_found(self, client, admin_headers, modules_dir):
        response = client.get(
            "/admin/modules/test/does_not_exist/review", headers=admin_headers
        )
        assert response.status_code == 404

    def test_audit_operator_allowed(self, client, operator_headers, modules_dir):
        _create_module(modules_dir, "test/audit_operator", ModuleStatus.VALIDATED.value)

        response = client.get(
            "/admin/modules/test/audit_operator/audit", headers=operator_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["module_id"] == "test/audit_operator"
        assert "attempts" in body

    def test_audit_requires_operator_viewer_forbidden(self, client, viewer_headers, modules_dir):
        _create_module(modules_dir, "test/audit_viewer", ModuleStatus.VALIDATED.value)
        response = client.get(
            "/admin/modules/test/audit_viewer/audit", headers=viewer_headers
        )
        assert response.status_code == 403
