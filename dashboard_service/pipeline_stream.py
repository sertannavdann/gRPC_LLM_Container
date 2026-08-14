"""
SSE Pipeline Stream - Server-Sent Events for live pipeline state.

Streams service health, module status, adapter health, tool-stage mappings,
and pipeline activity to the React Flow UI.
Uses FastAPI StreamingResponse with text/event-stream.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from shared.adapters import adapter_registry
from shared.modules.manifest import ModuleManifest, ModuleStatus

logger = logging.getLogger(__name__)

router = APIRouter()

# Modules directory scanned each cycle for on-disk (not necessarily loaded) modules.
MODULES_DIR = Path(os.getenv("MODULES_DIR", "/app/modules"))

# Tool → pipeline stage mapping (architectural relationships)
TOOL_STAGE_MAP = {
    "context_bridge": "tools",
    "user_context": "tools",
    "finance_query": "tools",
    "knowledge_search": "tools",
    "web_search": "tools",
    "web_loader": "tools",
    "code_executor": "tools",
    "module_builder": "tools",
    "module_manager": "tools",
    "module_installer": "tools",
    "module_validator": "tools",
    "math_solver": "tools",
    "destinations": "tools",
    "feature_test_harness": "tools",
}

# Tool → adapter category connections (which tools use which adapter categories)
TOOL_ADAPTER_MAP = {
    "context_bridge": ["weather", "calendar", "health", "navigation", "gaming"],
    "finance_query": ["finance"],
    "user_context": ["calendar", "health", "navigation"],
    "knowledge_search": [],
    "web_search": [],
    "web_loader": [],
    "code_executor": [],
    "module_builder": [],
    "module_manager": [],
    "module_installer": [],
    "module_validator": [],
    "math_solver": [],
    "destinations": ["navigation"],
    "feature_test_harness": [],
}


async def _check_service(client: httpx.AsyncClient, name: str, url: str) -> dict:
    """Probe a service health endpoint."""
    try:
        start = time.perf_counter()
        resp = await client.get(url, timeout=2.0)
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {
            "name": name,
            "state": "running" if resp.status_code == 200 else "error",
            "latency_ms": latency_ms,
            "status_code": resp.status_code,
        }
    except Exception:
        return {"name": name, "state": "error", "latency_ms": 0, "status_code": 0}


def _build_adapter_list(module_list: list, all_adapters: list) -> list:
    """Build adapter list with health status from registry."""
    adapters = []

    # Build module info lookup from pre-queried module list
    module_info = {}
    for m in module_list:
        mid = f"{m.get('category', '?')}/{m.get('platform', '?')}"
        module_info[mid] = m

    for info in all_adapters:
        adapter_id = f"{info.category}/{info.platform}"
        m_info = module_info.get(adapter_id, {})
        adapters.append({
            "id": adapter_id,
            "name": info.display_name or info.platform,
            "category": info.category,
            "platform": info.platform,
            "state": "running" if m_info.get("is_loaded", True) else "error",
            "requires_auth": info.requires_auth,
            "has_credentials": m_info.get("has_credentials", not info.requires_auth),
        })
    return adapters


def _build_tool_list(all_adapters: list) -> list:
    """Build tool list with stage and adapter connections."""
    tools = []
    for tool_name, stage in TOOL_STAGE_MAP.items():
        connected_categories = TOOL_ADAPTER_MAP.get(tool_name, [])
        # Resolve categories to actual adapter IDs
        connected_adapters = []
        for info in all_adapters:
            if info.category in connected_categories:
                connected_adapters.append(f"{info.category}/{info.platform}")
        tools.append({
            "name": tool_name,
            "stage": stage,
            "connected_adapters": connected_adapters,
        })
    return tools


def _build_pending_approval_list(modules_dir: Path) -> list[dict]:
    """
    Scan MODULES_DIR for on-disk manifests and build one entry per module.

    Runs every 2 seconds as part of the SSE cycle — must never raise, never
    block on network I/O, and must degrade to [] on any unexpected failure
    (T-08-13).
    """
    try:
        manifests = ModuleManifest.discover(modules_dir)
        entries = []
        for manifest in manifests:
            status = getattr(manifest.status, "value", manifest.status)
            if status == ModuleStatus.INSTALLED.value:
                state = "running"
            elif status == ModuleStatus.FAILED.value:
                state = "failed"
            else:
                state = "disabled"
            entries.append({
                "id": manifest.module_id,
                "name": manifest.display_name or manifest.name,
                "category": manifest.category,
                "status": status,
                "pending_approval": status == ModuleStatus.VALIDATED.value,
                "build_stage": status,
                "state": state,
            })
        return entries
    except Exception as e:
        logger.warning(f"Pending-approval manifest scan failed: {e}")
        return []


async def _build_pipeline_state(app) -> dict:
    """Build current pipeline state by probing services."""
    async with httpx.AsyncClient() as client:
        # Probe orchestrator only (dashboard is self-evidently running)
        checks = await asyncio.gather(
            _check_service(client, "orchestrator_admin", "http://orchestrator:8003/admin/health"),
            return_exceptions=True,
        )

    services = {}
    # Dashboard is always running if this SSE generator is executing
    services["dashboard"] = {
        "name": "dashboard",
        "state": "running",
        "latency_ms": 0,
        "status_code": 200,
    }
    for check in checks:
        if isinstance(check, dict):
            services[check["name"]] = check

    # gRPC services cannot be HTTP-probed — state is genuinely unknown
    for svc in ["llm_service", "chroma_service", "sandbox_service"]:
        services[svc] = {"name": svc, "state": "unknown", "latency_ms": 0}

    # Query data sources ONCE per cycle
    loader = getattr(app.state, "module_loader", None)
    module_list = loader.list_modules() if loader else []
    all_adapters = adapter_registry.list_all_flat()

    # Manifest scan merged in so a VALIDATED-but-never-loaded module is
    # visible (D-01/D-04) — by_id keyed on "category/platform".
    manifest_entries = _build_pending_approval_list(MODULES_DIR)
    by_id = {entry["id"]: entry for entry in manifest_entries}

    # Build module entries: loaded modules first, enriched with manifest
    # status/pending_approval/build_stage when available; then append
    # manifest-only entries not already present in the loaded set.
    modules = []
    loaded_ids = set()
    for m in module_list:
        mid = f"{m.get('category', '?')}/{m.get('platform', '?')}"
        loaded_ids.add(mid)
        manifest_info = by_id.get(mid)
        entry = {
            "id": mid,
            "name": m.get("name", "unknown"),
            "state": "running" if m.get("is_loaded") else "disabled",
            "category": m.get("category"),
        }
        if manifest_info is not None:
            entry["status"] = manifest_info["status"]
            entry["pending_approval"] = manifest_info["pending_approval"]
            entry["build_stage"] = manifest_info["build_stage"]
        else:
            entry["status"] = "installed"
            entry["pending_approval"] = False
            entry["build_stage"] = "installed"
        modules.append(entry)

    for entry in manifest_entries:
        if entry["id"] not in loaded_ids:
            modules.append(entry)

    # Pass cached data to helper functions
    adapters = _build_adapter_list(module_list, all_adapters)
    tools = _build_tool_list(all_adapters)

    # Stage → tool mapping
    stage_tools = {}
    for tool_name, stage in TOOL_STAGE_MAP.items():
        stage_tools.setdefault(stage, []).append(tool_name)

    return {
        "services": services,
        "modules": modules,
        "adapters": adapters,
        "adapters_count": len(adapters),
        "tools": tools,
        "stage_tools": stage_tools,
        "timestamp": time.time(),
    }


async def pipeline_event_generator(app) -> AsyncGenerator[str, None]:
    """Yield SSE events with pipeline state updates."""
    while True:
        try:
            state = await _build_pipeline_state(app)
            yield f"data: {json.dumps(state)}\n\n"
        except Exception as e:
            logger.warning(f"SSE state build error: {e}")
            yield f"data: {json.dumps({'error': str(e), 'timestamp': time.time()})}\n\n"
        await asyncio.sleep(2)  # 2-second update interval


@router.get("/stream/pipeline-state")
async def stream_pipeline(request: Request):
    """SSE endpoint for live pipeline state."""
    return StreamingResponse(
        pipeline_event_generator(request.app),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
