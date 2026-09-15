"""
Canvas context — Python port of ui_service/src/ecs/verbalize.ts (Phase 9, plan 02).

Re-derives the canvas c_state DSL server-side from the exact dict
`pipeline_stream._build_pipeline_state()` already computes every 2 seconds for
the SSE stream, so the orchestrator can fetch canvas context with NO browser
tab open (09-RESEARCH.md Pitfall 5).

Canonical ordering rule: sort by logical string id. Dict/insertion order is
NOT stable across dashboard restarts (or across dict rebuilds within a single
process), so `canonicalize()` — not iteration order — is the source of
ordering stability. This mirrors the JS spike (verbalize.mjs lines 12-14).

Grammar contract lives in ui_service/src/ecs/types.ts (C_STATE DSL GRAMMAR
doc comment) — this module implements it field-for-field and must not drift
from that contract without updating both ports.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def canonicalize(views: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort views by logical string id. Direct port of verbalize.mjs canonicalize()."""
    return sorted(views, key=lambda v: v["id"])


def pipeline_state_to_views(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Flatten a `_build_pipeline_state()`-shaped dict into canonical view records.

    No existing Python analog (09-PATTERNS.md "No Analog Found") — this is the
    server-side adapter that replaces the browser's live ECS world as the
    context-assembly source. Must never raise: each source collection is
    processed independently and degrades to being skipped on any unexpected
    failure, the same convention `_build_pending_approval_list` already
    honors since this runs inside the same 2-second cycle path.
    """
    views: List[Dict[str, Any]] = []

    try:
        services = state.get("services") or {}
        for name, svc in services.items():
            svc = svc or {}
            latency_ms = svc.get("latency_ms")
            views.append({
                "id": f"svc-{name}",
                "label": name,
                "kind": "service",
                "status": svc.get("state") or "unknown",
                "lifecycle": None,
                "detail": None,
                "latency": round(latency_ms) if latency_ms is not None else None,
                "creds": [],
                "flags": [],
            })
    except Exception as e:
        logger.warning(f"canvas_context: services flatten failed: {e}")

    try:
        modules = state.get("modules") or []
        for m in modules:
            m = m or {}
            flags = []
            if m.get("pending_approval"):
                flags.append("pending_approval")
            mid = m.get("id")
            views.append({
                "id": f"module-{mid}",
                "label": m.get("name") or "unknown",
                "kind": "module",
                "status": m.get("state") or "unknown",
                "lifecycle": m.get("status"),
                "detail": m.get("build_stage"),
                "latency": None,
                "creds": [],
                "flags": flags,
            })
    except Exception as e:
        logger.warning(f"canvas_context: modules flatten failed: {e}")

    try:
        adapters = state.get("adapters") or []
        for a in adapters:
            a = a or {}
            flags = []
            requires_auth = a.get("requires_auth")
            has_credentials = a.get("has_credentials")
            if requires_auth:
                flags.append("auth_required")
                if not has_credentials:
                    flags.append("no_credentials")
            aid = a.get("id")
            category = a.get("category")
            platform = a.get("platform")
            views.append({
                "id": f"adapter-{aid}",
                "label": a.get("name") or "unknown",
                "kind": "adapter",
                "status": a.get("state") or "unknown",
                "lifecycle": None,
                "detail": f"{category}/{platform}",
                "latency": None,
                "creds": [],
                "flags": flags,
            })
    except Exception as e:
        logger.warning(f"canvas_context: adapters flatten failed: {e}")

    try:
        tools = state.get("tools") or []
        for t in tools:
            t = t or {}
            connected = sorted(t.get("connected_adapters") or [])
            flags = [f"adapter:{a}" for a in connected]
            views.append({
                "id": f"tool-{t.get('name')}",
                "label": t.get("name") or "unknown",
                "kind": "tool",
                "status": "available",
                "lifecycle": None,
                "detail": t.get("stage"),
                "latency": None,
                "creds": [],
                "flags": flags,
            })
    except Exception as e:
        logger.warning(f"canvas_context: tools flatten failed: {e}")

    try:
        stage_tools = state.get("stage_tools") or {}
        for key in stage_tools.keys():
            views.append({
                "id": f"stage-{key}",
                "label": key,
                "kind": "stage",
                "status": "unknown",
                "lifecycle": None,
                "detail": None,
                "latency": None,
                "creds": [],
                "flags": [],
            })
    except Exception as e:
        logger.warning(f"canvas_context: stage_tools flatten failed: {e}")

    return views


def to_compact_dsl(views: List[Dict[str, Any]]) -> str:
    """
    Render canonical view records as the compact-DSL grammar defined in
    ui_service/src/ecs/types.ts. Grouped by kind (ascending), then by
    canonical logical-id order within each group.
    """
    rows = canonicalize(views)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for v in rows:
        groups.setdefault(v["kind"], []).append(v)

    lines = [
        '# pipeline_state — line format: <id> "<label>" <status>[/<lifecycle>]'
        "[ detail=<detail>][ latency=<ms>][ creds:<c1,c2>][ flags:<f1,f2>]"
    ]

    for kind in sorted(groups.keys()):
        lines.append(f"[{kind}]")
        for v in groups[kind]:
            label = str(v.get("label") or "").replace('"', "")
            line = f'{v["id"]} "{label}" {v.get("status")}'
            lifecycle = v.get("lifecycle")
            if lifecycle:
                line += f"/{lifecycle}"
            detail = v.get("detail")
            if detail:
                line += f" detail={detail}"
            latency = v.get("latency")
            if latency is not None:
                line += f" latency={latency}"
            creds = v.get("creds") or []
            if creds:
                line += f" creds:{','.join(creds)}"
            flags = v.get("flags") or []
            if flags:
                line += f" flags:{','.join(flags)}"
            lines.append(line)

    return "\n".join(lines)


def build_canvas_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """Build the `/context/canvas` response payload from a pipeline state dict."""
    views = pipeline_state_to_views(state)
    return {
        "c_state": to_compact_dsl(views),
        "timestamp": state.get("timestamp"),
        "entity_count": len(views),
    }
