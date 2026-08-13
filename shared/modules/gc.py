"""
Garbage-collection queue marker for terminally rejected modules (D-10).

Scope note (Phase 8 plan 08-01 deviation): this module is normally owned by
plan 08-02 (the retention/GC worker). Plan 08-01's terminal-reject path
(shared/modules/approval.py::reject_module) needs a stable import target
for `queue_for_gc()` today, so this file implements exactly the marker-file
contract described in 08-01's <interfaces> block — nothing more. The actual
background worker that consumes `.gc_pending` markers and purges heavyweight
artifacts is built in 08-02; do not add retention/sweep logic here.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

GC_MARKER_FILENAME = ".gc_pending"


def queue_for_gc(
    module_id: str,
    modules_dir: Union[str, Path],
    actor: Optional[str] = None,
) -> Path:
    """
    Queue a terminally rejected module's artifacts for garbage collection.

    Writes a `.gc_pending` marker JSON file inside the module directory:
        {module_id, rejected_at, actor}

    This function only records intent — it does not delete or move any
    files. The retention worker (08-02) is responsible for consuming these
    markers and purging artifacts once reference-safety is confirmed.

    Args:
        module_id: Module identifier in "category/platform" format
        modules_dir: Base modules directory (str or Path)
        actor: Identity of the actor who triggered the terminal rejection

    Returns:
        Path to the written marker file
    """
    category, platform = module_id.split("/", 1)
    module_dir = Path(modules_dir) / category / platform
    module_dir.mkdir(parents=True, exist_ok=True)

    marker = {
        "module_id": module_id,
        "rejected_at": datetime.now(timezone.utc).isoformat() + "Z",
        "actor": actor,
    }

    marker_path = module_dir / GC_MARKER_FILENAME
    marker_path.write_text(json.dumps(marker, indent=2))

    logger.info(f"Queued for GC: {module_id} (actor={actor})")

    return marker_path
