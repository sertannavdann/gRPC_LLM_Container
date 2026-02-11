"""
SSE Pipeline Stream - Server-Sent Events for live pipeline state.

Streams service health, module status, and pipeline activity to the
React Flow UI. Uses FastAPI StreamingResponse with text/event-stream.
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from shared.adapters import adapter_registry

logger = logging.getLogger(__name__)

router = APIRouter()

# Internal state cache (updated by polling)
_pipeline_state = {
    "services": {},
    "modules": [],
    "pipeline": {"active": False, "stage": None, "progress": 0},
    "timestamp": None,
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

    # Adapter count
    adapters = adapter_registry.list_all_flat()

    return {
        "services": services,
        "modules": modules,
        "adapters_count": len(adapters),
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
async def stream_pipeline(request):
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
