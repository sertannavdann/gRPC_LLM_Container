"""
SSE Pipeline Stream - Server-Sent Events for live pipeline state.

Streams service health, module status, adapter health, tool-stage mappings,
and pipeline activity to the React Flow UI.
Uses FastAPI StreamingResponse with text/event-stream.
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from shared.adapters import adapter_registry

logger = logging.getLogger(__name__)

router = APIRouter()

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


def _build_adapter_list(loader) -> list:
    """Build adapter list with health status from registry."""
    adapters = []
    all_flat = adapter_registry.list_all_flat()

    # Loader-based credential check
    module_info = {}
    if loader:
        for m in loader.list_modules():
            mid = f"{m.get('category', '?')}/{m.get('platform', '?')}"
            module_info[mid] = m

    for info in all_flat:
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


def _build_tool_list() -> list:
    """Build tool list with stage and adapter connections."""
    tools = []
    for tool_name, stage in TOOL_STAGE_MAP.items():
        connected_categories = TOOL_ADAPTER_MAP.get(tool_name, [])
        # Resolve categories to actual adapter IDs
        connected_adapters = []
        for info in adapter_registry.list_all_flat():
            if info.category in connected_categories:
                connected_adapters.append(f"{info.category}/{info.platform}")
        tools.append({
            "name": tool_name,
            "stage": stage,
            "connected_adapters": connected_adapters,
        })
    return tools


async def _build_pipeline_state(app) -> dict:
    """Build current pipeline state by probing services."""
    async with httpx.AsyncClient() as client:
        # Probe internal services
        checks = await asyncio.gather(
            _check_service(client, "dashboard", "http://localhost:8001/health"),
            _check_service(client, "orchestrator_admin", "http://orchestrator:8003/admin/health"),
            return_exceptions=True,
        )

    services = {}
    for check in checks:
        if isinstance(check, dict):
            services[check["name"]] = check

    # Static service entries (gRPC services can't be HTTP-probed easily)
    for svc in ["llm_service", "chroma_service", "sandbox_service"]:
        services[svc] = {"name": svc, "state": "idle", "latency_ms": 0}

    # Module info from loader
    loader = getattr(app.state, "module_loader", None)
    modules = []
    if loader:
        for m in loader.list_modules():
            modules.append({
                "id": f"{m.get('category', '?')}/{m.get('platform', '?')}",
                "name": m.get("name", "unknown"),
                "state": "running" if m.get("is_loaded") else "disabled",
                "category": m.get("category"),
            })

    # Adapter list with details
    adapters = _build_adapter_list(loader)

    # Tool list with stage mappings
    tools = _build_tool_list()

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
