"""
Unit tests for shared.audit.decorator — @audit_action.

Covers: sync + async capture, resource_id templating, snapshot before/after,
snapshot-exception tolerance, handler-exception -> no event, store-failure
-> HTTPException(500), actor resolution (contextvar > Request scan >
"system"/"default" fallback).
"""
import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from shared.audit import ActorContext, AuditStore, actor_context, audit_action
from shared.audit.store import AuditWriteError


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_audit_decorator.db")


@pytest.fixture
def store(tmp_db):
    return AuditStore(db_path=tmp_db)


def _make_request(user=None, org_id=None, client_host="127.0.0.1"):
    """Build a minimal Starlette Request with request.state.user/org_id set."""

    async def receive():
        return {"type": "http.request", "body": b""}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "headers": [],
        "client": (client_host, 12345),
    }
    request = Request(scope, receive)
    request.state.user = user
    request.state.org_id = org_id
    return request


class _User:
    def __init__(self, user_id):
        self.user_id = user_id


# ============================================================================
# Sync + async capture
# ============================================================================


class TestCapture:
    def test_sync_handler_records_event(self, store):
        @audit_action("widget_created", "widget", store=store)
        def create_widget(name: str):
            return {"name": name, "id": "w1"}

        with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
            result = create_widget(name="thing")

        assert result == {"name": "thing", "id": "w1"}
        events = store.query()
        assert len(events) == 1
        assert events[0]["action"] == "widget_created"
        assert events[0]["resource_type"] == "widget"
        assert events[0]["actor_id"] == "alice"
        assert events[0]["org_id"] == "org-1"

    def test_async_handler_records_event(self, store):
        @audit_action("widget_created", "widget", store=store)
        async def create_widget(name: str):
            await asyncio.sleep(0)
            return {"name": name, "id": "w2"}

        async def run():
            with actor_context(ActorContext(actor_id="bob", org_id="org-2")):
                return await create_widget(name="thing2")

        result = asyncio.run(run())
        assert result["id"] == "w2"
        events = store.query()
        assert len(events) == 1
        assert events[0]["actor_id"] == "bob"
        assert events[0]["org_id"] == "org-2"


# ============================================================================
# resource_id templating
# ============================================================================


class TestResourceIdTemplating:
    def test_template_over_bound_args(self, store):
        @audit_action(
            "module_enabled", "module", resource_id="{category}/{platform}", store=store
        )
        def enable(category: str, platform: str):
            return {"status": "ok"}

        with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
            enable(category="weather", platform="openweather")

        events = store.query()
        assert events[0]["resource_id"] == "weather/openweather"

    def test_template_failure_falls_back_to_raw_template(self, store):
        @audit_action("module_enabled", "module", resource_id="{missing_key}", store=store)
        def enable(category: str):
            return {"status": "ok"}

        with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
            enable(category="weather")

        events = store.query()
        # format() raised KeyError -> falls back to the raw template string
        assert events[0]["resource_id"] == "{missing_key}"


# ============================================================================
# Snapshot before/after
# ============================================================================


class TestSnapshot:
    def test_snapshot_before_and_after(self, store):
        calls = []

        def snap(widget_id: str):
            calls.append(widget_id)
            return {"widget_id": widget_id, "call_number": len(calls)}

        @audit_action("widget_updated", "widget", snapshot=snap, store=store)
        def update_widget(widget_id: str):
            return {"status": "ok"}

        with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
            update_widget(widget_id="w1")

        events = store.query()
        assert events[0]["before_state"] == {"widget_id": "w1", "call_number": 1}
        assert events[0]["after_state"] == {"widget_id": "w1", "call_number": 2}

    def test_snapshot_exception_tolerated(self, store, caplog):
        def bad_snap(widget_id: str):
            raise RuntimeError("boom")

        @audit_action("widget_updated", "widget", snapshot=bad_snap, store=store)
        def update_widget(widget_id: str):
            return {"status": "ok"}

        with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
            result = update_widget(widget_id="w1")

        assert result == {"status": "ok"}
        events = store.query()
        assert len(events) == 1
        assert events[0]["before_state"] is None
        assert events[0]["after_state"] is None

    def test_no_snapshot_uses_dict_result_as_after(self, store):
        @audit_action("widget_created", "widget", store=store)
        def create_widget():
            return {"id": "w9"}

        with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
            create_widget()

        events = store.query()
        assert events[0]["before_state"] is None
        assert events[0]["after_state"] == {"id": "w9"}

    def test_no_snapshot_non_dict_result_is_none(self, store):
        @audit_action("widget_deleted", "widget", store=store)
        def delete_widget():
            return "deleted"

        with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
            delete_widget()

        events = store.query()
        assert events[0]["after_state"] is None


# ============================================================================
# Handler exception -> no event recorded
# ============================================================================


class TestHandlerException:
    def test_sync_handler_exception_not_recorded(self, store):
        @audit_action("widget_created", "widget", store=store)
        def create_widget():
            raise ValueError("nope")

        with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
            with pytest.raises(ValueError):
                create_widget()

        assert store.query() == []

    def test_async_handler_exception_not_recorded(self, store):
        @audit_action("widget_created", "widget", store=store)
        async def create_widget():
            raise ValueError("nope")

        async def run():
            with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
                await create_widget()

        with pytest.raises(ValueError):
            asyncio.run(run())

        assert store.query() == []


# ============================================================================
# Store failure -> HTTPException(500)
# ============================================================================


class TestStoreFailure:
    def test_record_failure_raises_http_500(self, store, monkeypatch):
        def _boom(*args, **kwargs):
            raise AuditWriteError("disk full")

        monkeypatch.setattr(store, "record", _boom)

        @audit_action("widget_created", "widget", store=store)
        def create_widget():
            return {"id": "w1"}

        with actor_context(ActorContext(actor_id="alice", org_id="org-1")):
            with pytest.raises(HTTPException) as exc_info:
                create_widget()

        assert exc_info.value.status_code == 500


# ============================================================================
# Actor resolution
# ============================================================================


class TestActorResolution:
    def test_no_request_no_contextvar_falls_back_to_system(self, store):
        @audit_action("widget_created", "widget", store=store)
        def create_widget():
            return {"id": "w1"}

        create_widget()

        events = store.query()
        assert events[0]["actor_id"] == "system"
        assert events[0]["org_id"] == "default"

    def test_request_scan_used_when_no_contextvar(self, store):
        request = _make_request(user=_User("carol"), org_id="org-3")

        @audit_action("widget_created", "widget", store=store)
        def create_widget(request: Request):
            return {"id": "w1"}

        create_widget(request=request)

        events = store.query()
        assert events[0]["actor_id"] == "carol"
        assert events[0]["org_id"] == "org-3"
        assert events[0]["ip_address"] == "127.0.0.1"

    def test_contextvar_wins_over_request_scan(self, store):
        request = _make_request(user=_User("carol"), org_id="org-3")

        @audit_action("widget_created", "widget", store=store)
        def create_widget(request: Request):
            return {"id": "w1"}

        with actor_context(ActorContext(actor_id="dave", org_id="org-4")):
            create_widget(request=request)

        events = store.query()
        assert events[0]["actor_id"] == "dave"
        assert events[0]["org_id"] == "org-4"

    def test_request_present_but_no_user_falls_back_to_system(self, store):
        request = _make_request(user=None, org_id=None)

        @audit_action("widget_created", "widget", store=store)
        def create_widget(request: Request):
            return {"id": "w1"}

        create_widget(request=request)

        events = store.query()
        assert events[0]["actor_id"] == "system"
        assert events[0]["org_id"] == "default"
