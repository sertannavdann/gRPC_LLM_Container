"""
Audit capture parity integration tests (REQ-011, Phase 07-02 Task 3).

Covers cross-path capture parity: @audit_action-decorated Admin API
mutations, DevModeAuditLog's SQLite dual-write, and direct record() calls
from chat-tool strategies under ambient actor context.

All tests use FastAPI TestClient (in-process, no Docker) via the shared
create_test_admin_app() factory. Like other tests in this directory, the
suite is gated by the parent tests/integration/conftest.py autouse
`test_environment` fixture, which requires the orchestrator gRPC service to
be reachable on port 50054 (skips otherwise — see test_module_crud.py for
the identical, pre-existing pattern).
"""
from pathlib import Path

import pytest

from shared.audit import ActorContext, AuditWriteError, actor_context
from shared.modules.audit import DevModeAuditLog
from shared.modules.manifest import ModuleManifest, ModuleStatus


def _create_module(modules_dir: Path, module_id: str, status: str) -> ModuleManifest:
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


class TestHTTPMutationCapture:
    """@audit_action-decorated Admin API mutations record events (D-05)."""

    def test_config_mutation_records_actor_org_ip(
        self, client, admin_headers, audit_store, config_manager
    ):
        """PUT /admin/routing-config records actor_id, org scoping, and IP (via
        AuditContextMiddleware reading request.state.user/org_id)."""
        payload = config_manager.get_config().model_dump()
        payload["version"] = "2.0"

        response = client.put("/admin/routing-config", json=payload, headers=admin_headers)
        assert response.status_code == 200

        events = audit_store.query(action="routing_config_updated")
        assert len(events) == 1
        event = events[0]
        assert event["actor_id"]  # resolved from the calling API key's user
        assert event["org_id"] == "test-org"
        assert event["ip_address"] is not None
        assert event["after_state"]["version"] == "2.0"

    def test_module_mutation_records_event(
        self, client, admin_headers, audit_store, modules_dir
    ):
        """POST /admin/modules/{cat}/{plat}/enable records a module_enabled event."""
        _create_module(modules_dir, "test/capture", ModuleStatus.APPROVED.value)

        response = client.post("/admin/modules/test/capture/enable", headers=admin_headers)
        assert response.status_code == 200

        events = audit_store.query(action="module_enabled")
        assert len(events) == 1
        assert events[0]["resource_id"] == "test/capture"

    def test_handler_exception_not_recorded(self, client, admin_headers, audit_store):
        """Enabling a nonexistent module raises inside the handler — no audit event."""
        response = client.post(
            "/admin/modules/nonexistent/platform/enable", headers=admin_headers
        )
        assert response.status_code == 500
        assert audit_store.query(action="module_enabled") == []

    def test_store_failure_returns_500_and_event_count_unchanged(
        self, client, admin_headers, audit_store, config_manager, monkeypatch
    ):
        """A broken AuditStore.record() surfaces as HTTP 500 (fail-closed, D-03)
        and does not add a row (the write itself failed)."""
        before_count = audit_store.count()

        def _boom(*args, **kwargs):
            raise AuditWriteError("disk full")

        monkeypatch.setattr(audit_store, "record", _boom)

        payload = config_manager.get_config().model_dump()
        payload["version"] = "3.0"
        response = client.put("/admin/routing-config", json=payload, headers=admin_headers)

        assert response.status_code == 500
        assert "Audit write failed" in response.json()["detail"]
        assert audit_store.count() == before_count


class TestCredentialRedaction:
    """Credential mutation events never carry raw secret values (D-04)."""

    def test_credential_mutation_carries_key_names_only(
        self, client, owner_headers, audit_store, tmp_databases
    ):
        response = client.post(
            "/admin/modules/test/creds/credentials",
            json={"credentials": {"api_key": "super-secret-plaintext-value"}},
            headers=owner_headers,
        )
        assert response.status_code == 200

        events = audit_store.query(action="module_credentials_stored")
        assert len(events) == 1
        event = events[0]

        # The snapshot only ever carried {"field_names": [...]}
        assert event["after_state"] == {"field_names": ["api_key"]}
        assert event["before_state"] == {"field_names": ["api_key"]}

        # Raw secret value never touches the DB file on disk.
        raw_db_bytes = Path(tmp_databases["audit"]).read_bytes()
        assert b"super-secret-plaintext-value" not in raw_db_bytes


class TestDevModeAuditLogDualWrite:
    """DevModeAuditLog dual-writes JSONL + SQLite when constructed with a sink (D-01)."""

    def test_log_action_dual_writes_to_sink(self, audit_store, tmp_path):
        log = DevModeAuditLog(audit_dir=tmp_path / "audit", sink=audit_store)

        event_id = log.log_action(
            action="draft_created", actor="dev1", module_id="test/x", draft_id="d1"
        )

        # JSONL side
        jsonl_events = log.get_events()
        assert any(e.event_id == event_id for e in jsonl_events)

        # SQLite side, cross-referenced by jsonl_event_id
        sqlite_events = audit_store.query(action="draft_created")
        assert len(sqlite_events) == 1
        sqlite_event = sqlite_events[0]
        assert sqlite_event["resource_type"] == "module_draft"
        assert sqlite_event["resource_id"] == "d1"
        assert sqlite_event["details"]["jsonl_event_id"] == event_id
        assert sqlite_event["details"]["module_id"] == "test/x"
        assert sqlite_event["details"]["draft_id"] == "d1"

    def test_log_action_without_draft_id_uses_module_resource(self, audit_store, tmp_path):
        log = DevModeAuditLog(audit_dir=tmp_path / "audit", sink=audit_store)

        log.log_action(action="module_promoted", actor="dev1", module_id="test/y")

        sqlite_events = audit_store.query(action="module_promoted")
        assert len(sqlite_events) == 1
        assert sqlite_events[0]["resource_type"] == "module"
        assert sqlite_events[0]["resource_id"] == "test/y"

    def test_log_action_sink_failure_propagates(self, audit_store, tmp_path, monkeypatch):
        """Sink failure is NOT swallowed — no try/except around sink.record (D-03).
        The JSONL append already happened before the sink call raises."""

        def _boom(*args, **kwargs):
            raise AuditWriteError("sink unavailable")

        monkeypatch.setattr(audit_store, "record", _boom)

        log = DevModeAuditLog(audit_dir=tmp_path / "audit", sink=audit_store)

        with pytest.raises(AuditWriteError):
            log.log_action(action="draft_created", actor="dev1", module_id="test/z")

        # The JSONL line was still written (append happens before the sink call).
        assert len(log.get_events()) == 1


class TestChatToolActorCapture:
    """Chat-tool mutations resolve actor identity from the ambient contextvar (D-05)."""

    def test_enable_strategy_records_chat_actor(self, audit_store):
        from unittest.mock import MagicMock

        from tools.builtin.module_admin import EnableStrategy

        module_loader = MagicMock()
        handle = MagicMock(is_loaded=True, error=None)
        module_loader.enable_module.return_value = handle

        strategy = EnableStrategy(
            module_loader=module_loader, module_registry=None, audit_store=audit_store
        )

        with actor_context(
            ActorContext(actor_id="user-42", org_id="org-chat", channel="chat")
        ):
            result = strategy.execute(module_id="test/chatenable")

        assert result["status"] == "success"
        events = audit_store.query(action="module_enabled", resource_id="test/chatenable")
        assert len(events) == 1
        assert events[0]["actor_id"] == "user-42"
        assert events[0]["org_id"] == "org-chat"

    def test_enable_strategy_falls_back_to_chat_agent_without_context(self, audit_store):
        from unittest.mock import MagicMock

        from tools.builtin.module_admin import EnableStrategy

        module_loader = MagicMock()
        handle = MagicMock(is_loaded=True, error=None)
        module_loader.enable_module.return_value = handle

        strategy = EnableStrategy(
            module_loader=module_loader, module_registry=None, audit_store=audit_store
        )

        # No ambient actor_context — falls back to "chat_agent"/"default".
        result = strategy.execute(module_id="test/chatnocontext")

        assert result["status"] == "success"
        events = audit_store.query(
            action="module_enabled", resource_id="test/chatnocontext"
        )
        assert len(events) == 1
        assert events[0]["actor_id"] == "chat_agent"
        assert events[0]["org_id"] == "default"

    def test_credential_strategy_never_records_raw_value(self, audit_store, tmp_path):
        from unittest.mock import MagicMock

        from tools.builtin.module_admin import CredentialStrategy

        credential_store = MagicMock()
        strategy = CredentialStrategy(
            credential_store=credential_store, module_loader=None, audit_store=audit_store
        )

        result = strategy.execute(module_id="test/chatcreds", api_key="another-secret-value")

        assert result["status"] == "success"
        events = audit_store.query(
            action="module_credentials_stored", resource_id="test/chatcreds"
        )
        assert len(events) == 1
        assert events[0]["details"] == {"field_names": ["api_key"]}

    def test_strategy_fails_closed_on_audit_write_error(self, audit_store, monkeypatch):
        from unittest.mock import MagicMock

        from tools.builtin.module_admin import EnableStrategy

        def _boom(*args, **kwargs):
            raise AuditWriteError("disk full")

        monkeypatch.setattr(audit_store, "record", _boom)

        module_loader = MagicMock()
        handle = MagicMock(is_loaded=True, error=None)
        module_loader.enable_module.return_value = handle

        strategy = EnableStrategy(
            module_loader=module_loader, module_registry=None, audit_store=audit_store
        )

        result = strategy.execute(module_id="test/chatfail")

        assert result == {"status": "error", "error": "audit write failed"}
