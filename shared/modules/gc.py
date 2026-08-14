"""
Garbage-collection sweep for terminally rejected modules (D-10, D-12).

`queue_for_gc()` (Phase 8 plan 08-01) writes a `.gc_pending` marker file into
a rejected module's directory recording {module_id, rejected_at, actor}. This
module (Phase 8 plan 08-04) is the consumer: `sweep_gc_pending()` finds every
marker under `modules_dir`, and `purge_module_artifacts()` deletes the
heavyweight module directory and its associated artifact bundle directory
UNLESS an `active_versions` rollback pointer still references the module
(D-12 reference-safety check).

HARD CONSTRAINT (07-CONTEXT D-01 / T-08-15): the audit trail is GC-exempt.
This module never opens AUDIT_DB_PATH, never scans AUDIT_DIR, and any
`*.jsonl` file discovered inside a module directory being purged is
relocated (never deleted) before the directory is removed.
"""
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

GC_MARKER_FILENAME = ".gc_pending"
GC_PRESERVED_DIRNAME = ".gc_preserved"


def queue_for_gc(
    module_id: str,
    modules_dir: Union[str, Path],
    actor: Optional[str] = None,
) -> Optional[Path]:
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
        Path to the written marker file, or None if module_dir does not
        exist (IN-04 — this function must never fabricate a phantom
        directory for a bogus/nonexistent module_id)
    """
    category, platform = module_id.split("/", 1)
    module_dir = Path(modules_dir) / category / platform

    if not module_dir.exists():
        logger.warning(
            f"Cannot queue for GC: module directory does not exist for {module_id} "
            f"({module_dir})"
        )
        return None

    marker = {
        "module_id": module_id,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
    }

    marker_path = module_dir / GC_MARKER_FILENAME
    marker_path.write_text(json.dumps(marker, indent=2))

    logger.info(f"Queued for GC: {module_id} (actor={actor})")

    return marker_path


def _resolved_child(base: Path, *parts: str) -> Path:
    """Resolve base/parts and assert the result stays inside base (T-08-14)."""
    base_resolved = base.resolve()
    candidate = base_resolved.joinpath(*parts).resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise ValueError(
            f"Refusing to operate outside {base_resolved}: resolved to {candidate}"
        )
    return candidate


def purge_module_artifacts(
    module_id: str,
    modules_dir: Union[str, Path],
    artifacts_dir: Union[str, Path],
    version_manager=None,
) -> dict:
    """
    Delete a terminally rejected module's heavyweight artifacts (D-10).

    Reference-safety check (D-12): if `version_manager` reports version rows
    for this module AND an active_versions pointer is still set, nothing is
    deleted. If version rows exist but there is no active pointer, the
    module is purged. If there are no version rows at all, the module is
    purged unconditionally (RESEARCH Pitfall 5 — most rejected modules never
    reach record_version()).

    Never deletes `*.jsonl` files or anything outside `modules_dir` /
    `artifacts_dir` — `*.jsonl` files found inside the module directory are
    relocated to `modules_dir/.gc_preserved/{category}_{platform}/` before
    the directory is removed.

    Args:
        module_id: Module identifier in "category/platform" format
        modules_dir: Base modules directory
        artifacts_dir: Base artifact-bundle directory
        version_manager: Optional VersionManager for the reference-safety
            check (list_versions / get_active_version)

    Returns:
        dict describing the outcome — either
        {"purged": False, "reason": "active_version_reference"} or
        {"purged": True, "module_id": ..., "removed": [...], "preserved": [...]}
    """
    if "/" not in module_id:
        raise ValueError(f"module_id must be 'category/platform', got: {module_id!r}")
    category, platform = module_id.split("/", 1)
    if ".." in (category, platform) or not category or not platform:
        raise ValueError(f"Unsafe module_id rejected: {module_id!r}")

    modules_dir = Path(modules_dir)
    artifacts_dir = Path(artifacts_dir)

    # D-12: reference-safety check before every delete.
    if version_manager is not None:
        try:
            versions = version_manager.list_versions(module_id)
        except Exception as e:
            logger.warning(f"GC: list_versions failed for {module_id}: {e}")
            versions = []
        if versions:
            try:
                active = version_manager.get_active_version(module_id)
            except Exception as e:
                logger.warning(f"GC: get_active_version failed for {module_id}: {e}")
                active = None
            if active is not None:
                logger.info(
                    f"GC: skipping {module_id} — protected by active_versions pointer"
                )
                return {"purged": False, "reason": "active_version_reference"}

    removed: list = []
    preserved: list = []

    # Module directory (modules_dir/{category}/{platform})
    module_dir = _resolved_child(modules_dir, category, platform)
    if module_dir.exists():
        preserved_root = _resolved_child(modules_dir, GC_PRESERVED_DIRNAME, f"{category}_{platform}")
        jsonl_files = list(module_dir.rglob("*.jsonl"))
        if jsonl_files:
            preserved_root.mkdir(parents=True, exist_ok=True)
            for f in jsonl_files:
                rel = f.relative_to(module_dir)
                dest = preserved_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                preserved.append(str(dest))
        shutil.rmtree(module_dir)
        removed.append(str(module_dir))
    else:
        logger.info(f"GC: module directory already absent for {module_id} ({module_dir})")

    # Artifact bundle directory (artifacts_dir/{category}/{platform})
    artifact_dir = _resolved_child(artifacts_dir, category, platform)
    if artifact_dir.exists():
        jsonl_files = list(artifact_dir.rglob("*.jsonl"))
        if jsonl_files:
            preserved_root = _resolved_child(modules_dir, GC_PRESERVED_DIRNAME, f"{category}_{platform}")
            preserved_root.mkdir(parents=True, exist_ok=True)
            for f in jsonl_files:
                rel = f.relative_to(artifact_dir)
                dest = preserved_root / "artifacts" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                preserved.append(str(dest))
        shutil.rmtree(artifact_dir)
        removed.append(str(artifact_dir))

    logger.info(f"GC: purged {module_id} — removed={removed} preserved={preserved}")

    return {
        "purged": True,
        "module_id": module_id,
        "removed": removed,
        "preserved": preserved,
    }


def sweep_gc_pending(
    modules_dir: Union[str, Path],
    artifacts_dir: Union[str, Path],
    version_manager=None,
    grace_seconds: int = 0,
) -> dict:
    """
    Find every `.gc_pending` marker under `modules_dir` and purge or protect
    the corresponding module's artifacts.

    Each marker is processed independently inside its own try/except so one
    malformed marker or one failing purge can never abort the sweep for the
    rest. Never touches AUDIT_DIR, `*.jsonl`, or `*.db` files.

    Args:
        modules_dir: Base modules directory to rglob for markers
        artifacts_dir: Base artifact-bundle directory
        version_manager: Optional VersionManager for reference-safety checks
        grace_seconds: Markers whose `rejected_at` is newer than
            `now - grace_seconds` are skipped this pass (no error recorded)

    Returns:
        {"scanned": n, "purged": [module_id, ...], "protected": [module_id, ...],
         "errors": [{"module_id"|"marker": ..., "error": str}, ...]}
    """
    modules_dir = Path(modules_dir)
    summary: dict = {"scanned": 0, "purged": [], "protected": [], "errors": []}

    if not modules_dir.exists():
        return summary

    now = datetime.now(timezone.utc)

    for marker_path in modules_dir.rglob(GC_MARKER_FILENAME):
        summary["scanned"] += 1
        module_id = None
        try:
            data = json.loads(marker_path.read_text())
            module_id = data.get("module_id")
            rejected_at_raw = data.get("rejected_at")

            if not module_id:
                raise ValueError(f"Marker missing module_id: {marker_path}")

            # An unparseable rejected_at timestamp does not abort the sweep —
            # the error is recorded and the module is still processed below
            # (grace period simply does not apply to it).
            rejected_at = None
            if rejected_at_raw:
                try:
                    rejected_at = datetime.fromisoformat(rejected_at_raw)
                    if rejected_at.tzinfo is None:
                        rejected_at = rejected_at.replace(tzinfo=timezone.utc)
                except ValueError as e:
                    summary["errors"].append(
                        {"module_id": module_id, "error": f"unparseable rejected_at: {e}"}
                    )

            if grace_seconds > 0 and rejected_at is not None:
                age_seconds = (now - rejected_at).total_seconds()
                if age_seconds < grace_seconds:
                    continue

            result = purge_module_artifacts(
                module_id, modules_dir, artifacts_dir, version_manager=version_manager
            )
            if result.get("purged"):
                summary["purged"].append(module_id)
            else:
                summary["protected"].append(module_id)

        except Exception as e:
            logger.warning(f"GC: sweep error for marker {marker_path}: {e}")
            summary["errors"].append(
                {"module_id": module_id, "marker": str(marker_path), "error": str(e)}
            )

    return summary
