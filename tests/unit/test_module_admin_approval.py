"""
Tests for the chat half of D-02/D-17 (Phase 8 Plan 10):

- shared.auth.session_context: contextvar round-trip / contextmanager reset
- orchestrator._resolve_session_user (the testable core of
  OrchestratorService._get_session_user): x-api-key gRPC metadata resolution
- tools.builtin.module_admin.ApproveModuleStrategy / RejectModuleStrategy:
  RBAC-guarded chat approve/reject actions on ModuleAdminTool
"""
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from shared.auth.models import Role, User
from shared.auth.session_context import (
    SessionAuthError,
    get_session_user,
    reset_session_user,
    session_user,
    set_session_user,
)


# ─── Task 1: session_context round-trip + contextmanager ──────────────────


class TestSessionContextRoundTrip:
    def test_get_session_user_returns_none_outside_scope(self):
        assert get_session_user() is None

    def test_set_get_round_trip(self):
        user = User(user_id="u1", org_id="org1", role=Role.ADMIN)
        token = set_session_user(user)
        try:
            assert get_session_user() is user
        finally:
            reset_session_user(token)
        assert get_session_user() is None

    def test_session_user_contextmanager_round_trip(self):
        user = User(user_id="u2", org_id="org2", role=Role.OPERATOR)
        assert get_session_user() is None
        with session_user(user) as yielded:
            assert yielded is user
            assert get_session_user() is user
        assert get_session_user() is None

    def test_session_user_contextmanager_resets_on_exception(self):
        user = User(user_id="u3", org_id="org3", role=Role.VIEWER)
        with pytest.raises(ValueError):
            with session_user(user):
                assert get_session_user() is user
                raise ValueError("boom")
        assert get_session_user() is None

    def test_session_auth_error_is_exception(self):
        assert issubclass(SessionAuthError, Exception)


# ─── Task 1: _resolve_session_user (gRPC metadata -> User) ────────────────


class _StubContext:
    """Stub grpc.ServicerContext exposing only invocation_metadata()."""

    def __init__(self, metadata: Optional[List[Tuple[str, Any]]] = None, raise_exc: bool = False):
        self._metadata = metadata
        self._raise = raise_exc

    def invocation_metadata(self):
        if self._raise:
            raise RuntimeError("metadata unavailable")
        return self._metadata or []


class _StubAPIKeyStore:
    def __init__(self, valid_keys: Optional[Dict[str, User]] = None, raise_exc: bool = False):
        self._valid_keys = valid_keys or {}
        self._raise = raise_exc
        self.validated_keys: List[str] = []

    def validate_key(self, key_plaintext: str) -> Optional[User]:
        self.validated_keys.append(key_plaintext)
        if self._raise:
            raise RuntimeError("store unavailable")
        return self._valid_keys.get(key_plaintext)


class TestResolveSessionUser:
    def _import_resolver(self):
        from orchestrator.orchestrator_service import _resolve_session_user
        return _resolve_session_user

    def test_valid_key_resolves_user(self):
        resolve = self._import_resolver()
        user = User(user_id="admin1", org_id="org1", role=Role.ADMIN)
        store = _StubAPIKeyStore(valid_keys={"secret-key": user})
        ctx = _StubContext(metadata=[("x-api-key", "secret-key")])

        resolved = resolve(ctx, store)
        assert resolved is user

    def test_valid_key_bytes_value_resolves_user(self):
        resolve = self._import_resolver()
        user = User(user_id="admin1", org_id="org1", role=Role.ADMIN)
        store = _StubAPIKeyStore(valid_keys={"secret-key": user})
        ctx = _StubContext(metadata=[("x-api-key", b"secret-key")])

        resolved = resolve(ctx, store)
        assert resolved is user

    def test_missing_metadata_returns_none(self):
        resolve = self._import_resolver()
        store = _StubAPIKeyStore()
        ctx = _StubContext(metadata=[])

        assert resolve(ctx, store) is None
        assert store.validated_keys == []

    def test_unknown_key_returns_none_never_raises(self):
        resolve = self._import_resolver()
        store = _StubAPIKeyStore(valid_keys={})
        ctx = _StubContext(metadata=[("x-api-key", "unknown-key")])

        assert resolve(ctx, store) is None

    def test_no_store_configured_returns_none(self):
        resolve = self._import_resolver()
        ctx = _StubContext(metadata=[("x-api-key", "any-key")])

        assert resolve(ctx, None) is None

    def test_store_raising_returns_none_never_raises(self):
        resolve = self._import_resolver()
        store = _StubAPIKeyStore(raise_exc=True)
        ctx = _StubContext(metadata=[("x-api-key", "secret-key")])

        assert resolve(ctx, store) is None

    def test_metadata_lookup_raising_returns_none(self):
        resolve = self._import_resolver()
        store = _StubAPIKeyStore()
        ctx = _StubContext(raise_exc=True)

        assert resolve(ctx, store) is None

    def test_key_lookup_is_case_insensitive_on_header_name(self):
        resolve = self._import_resolver()
        user = User(user_id="admin1", org_id="org1", role=Role.ADMIN)
        store = _StubAPIKeyStore(valid_keys={"secret-key": user})
        ctx = _StubContext(metadata=[("X-Api-Key", "secret-key")])

        assert resolve(ctx, store) is user


# ─── Task 2: ApproveModuleStrategy / RejectModuleStrategy RBAC ────────────


class _StubAuditLog:
    """Stub DevModeAuditLog capturing log_action() calls."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def log_action(self, action, actor, module_id=None, draft_id=None, details=None):
        self.calls.append(
            {
                "action": action,
                "actor": actor,
                "module_id": module_id,
                "draft_id": draft_id,
                "details": details or {},
            }
        )
        return "stub-event-id"


@pytest.fixture
def tmp_modules_dir():
    tmpdir = tempfile.mkdtemp()
    modules_dir = Path(tmpdir) / "modules"
    modules_dir.mkdir()
    yield modules_dir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def validated_module(tmp_modules_dir):
    """Write a VALIDATED manifest for module_id 'test/example'."""
    from shared.modules.manifest import ModuleManifest, ModuleStatus

    mod_dir = tmp_modules_dir / "test" / "example"
    mod_dir.mkdir(parents=True)
    (mod_dir / "adapter.py").write_text("class ExampleAdapter:\n    pass\n")
    (mod_dir / "test_adapter.py").write_text("def test_example():\n    assert True\n")

    manifest = ModuleManifest(
        name="example",
        category="test",
        platform="example",
        status=ModuleStatus.VALIDATED.value,
    )
    manifest.save(tmp_modules_dir)
    return "test/example"


def _load_status(tmp_modules_dir, module_id):
    manifest_path = tmp_modules_dir / module_id.replace("/", "/") / "manifest.json"
    # module_id is "category/platform"
    category, platform = module_id.split("/", 1)
    manifest_path = tmp_modules_dir / category / platform / "manifest.json"
    data = json.loads(manifest_path.read_text())
    return data["status"]


@pytest.fixture
def strategies(tmp_modules_dir):
    from tools.builtin.module_admin import ApproveModuleStrategy, RejectModuleStrategy

    audit_log = _StubAuditLog()
    approve = ApproveModuleStrategy(audit_log=audit_log, modules_dir=tmp_modules_dir)
    reject = RejectModuleStrategy(audit_log=audit_log, modules_dir=tmp_modules_dir)
    return approve, reject, audit_log


class TestApproveModuleStrategy:
    def test_admin_can_approve(self, strategies, validated_module, tmp_modules_dir):
        approve, _reject, audit_log = strategies
        admin = User(user_id="admin-1", org_id="org-1", role=Role.ADMIN)

        with session_user(admin):
            result = approve.execute(action="approve_module", module_id=validated_module)

        assert result["status"] == "success"
        assert result["new_status"] == "approved"
        assert _load_status(tmp_modules_dir, validated_module) == "approved"
        assert audit_log.calls
        assert audit_log.calls[-1]["actor"] == "admin-1"

    def test_operator_denied(self, strategies, validated_module, tmp_modules_dir):
        approve, _reject, _audit_log = strategies
        operator = User(user_id="op-1", org_id="org-1", role=Role.OPERATOR)

        with session_user(operator):
            result = approve.execute(action="approve_module", module_id=validated_module)

        assert result["status"] == "error"
        assert "write_config" in result["error"] or "permission" in result["error"].lower()
        assert _load_status(tmp_modules_dir, validated_module) == "validated"

    def test_viewer_denied(self, strategies, validated_module, tmp_modules_dir):
        approve, _reject, _audit_log = strategies
        viewer = User(user_id="view-1", org_id="org-1", role=Role.VIEWER)

        with session_user(viewer):
            result = approve.execute(action="approve_module", module_id=validated_module)

        assert result["status"] == "error"
        assert _load_status(tmp_modules_dir, validated_module) == "validated"

    def test_no_session_denied(self, strategies, validated_module, tmp_modules_dir):
        approve, _reject, _audit_log = strategies

        result = approve.execute(action="approve_module", module_id=validated_module)

        assert result["status"] == "error"
        assert "authenticated" in result["error"].lower()
        assert _load_status(tmp_modules_dir, validated_module) == "validated"

    def test_never_hardcodes_chat_agent_actor(self, strategies, validated_module):
        approve, _reject, audit_log = strategies
        admin = User(user_id="real-admin-id", org_id="org-1", role=Role.ADMIN)

        with session_user(admin):
            approve.execute(action="approve_module", module_id=validated_module)

        assert audit_log.calls[-1]["actor"] == "real-admin-id"
        assert audit_log.calls[-1]["actor"] != "chat_agent"


class TestRejectModuleStrategy:
    def test_admin_reject_with_feedback_triggers_repair_path(
        self, strategies, validated_module, tmp_modules_dir
    ):
        _approve, reject, audit_log = strategies
        admin = User(user_id="admin-1", org_id="org-1", role=Role.ADMIN)

        with session_user(admin):
            result = reject.execute(
                action="reject_module",
                module_id=validated_module,
                feedback="fix the auth header",
            )

        assert result["status"] == "success"
        assert result["new_status"] == "validating"
        assert _load_status(tmp_modules_dir, validated_module) == "validating"
        assert audit_log.calls[-1]["actor"] == "admin-1"

    def test_admin_reject_without_feedback_is_terminal(
        self, strategies, validated_module, tmp_modules_dir
    ):
        _approve, reject, audit_log = strategies
        admin = User(user_id="admin-1", org_id="org-1", role=Role.ADMIN)

        with session_user(admin):
            result = reject.execute(action="reject_module", module_id=validated_module)

        assert result["status"] == "success"
        assert result["new_status"] == "failed"
        assert _load_status(tmp_modules_dir, validated_module) == "failed"

    def test_operator_denied(self, strategies, validated_module, tmp_modules_dir):
        _approve, reject, _audit_log = strategies
        operator = User(user_id="op-1", org_id="org-1", role=Role.OPERATOR)

        with session_user(operator):
            result = reject.execute(action="reject_module", module_id=validated_module)

        assert result["status"] == "error"
        assert _load_status(tmp_modules_dir, validated_module) == "validated"

    def test_viewer_denied(self, strategies, validated_module, tmp_modules_dir):
        _approve, reject, _audit_log = strategies
        viewer = User(user_id="view-1", org_id="org-1", role=Role.VIEWER)

        with session_user(viewer):
            result = reject.execute(action="reject_module", module_id=validated_module)

        assert result["status"] == "error"
        assert _load_status(tmp_modules_dir, validated_module) == "validated"

    def test_no_session_denied(self, strategies, validated_module, tmp_modules_dir):
        _approve, reject, _audit_log = strategies

        result = reject.execute(action="reject_module", module_id=validated_module)

        assert result["status"] == "error"
        assert "authenticated" in result["error"].lower()
        assert _load_status(tmp_modules_dir, validated_module) == "validated"

    def test_never_hardcodes_chat_agent_actor(self, strategies, validated_module):
        _approve, reject, audit_log = strategies
        admin = User(user_id="real-admin-id", org_id="org-1", role=Role.ADMIN)

        with session_user(admin):
            reject.execute(action="reject_module", module_id=validated_module)

        assert audit_log.calls[-1]["actor"] == "real-admin-id"
        assert audit_log.calls[-1]["actor"] != "chat_agent"
