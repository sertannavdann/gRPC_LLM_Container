"""
Module approval core (D-16/D-17/D-09/D-10/D-19).

Single source of truth for approve/reject decisions. Both the HTTP admin
endpoints (orchestrator/admin_api.py) and the chat approval strategy (08-08)
call these functions directly, so approval semantics are defined once and
enforced identically regardless of entry point.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

from shared.modules.artifacts import compute_code_bundle_hash
from shared.modules.gc import queue_for_gc
from shared.modules.manifest import ModuleManifest, ModuleStatus

logger = logging.getLogger(__name__)


def _resolve_manifest_path(module_id: str, modules_dir: Union[str, Path]) -> Path:
    category, platform = module_id.split("/", 1)
    return Path(modules_dir) / category / platform / "manifest.json"


def _bundle_hash(module_id: str, modules_dir: Union[str, Path]) -> Optional[str]:
    """
    Best-effort code-bundle hash resolution via the shared
    compute_code_bundle_hash() helper (manifest.json-exclusive, CR-01 fix).
    Returns None if files are missing or hashing fails — approval/rejection
    must never be blocked by hash resolution.
    """
    try:
        category, platform = module_id.split("/", 1)
        module_dir = Path(modules_dir) / category / platform
        return compute_code_bundle_hash(module_dir, module_id)
    except Exception as e:
        logger.warning(f"Could not compute bundle hash for {module_id}: {e}")
        return None


def approve_module(
    module_id: str,
    actor: str,
    audit_log: Any,
    modules_dir: Union[str, Path],
    org_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Approve a VALIDATED module, moving it to APPROVED (D-16/D-17).

    Callers MUST have already enforced admin+ RBAC (WRITE_CONFIG) before
    reaching this function — this function itself performs no auth check.
    Every decision is recorded via audit_log.log_action with actor,
    timestamp, and bundle hash (D-19).

    Args:
        module_id: Module identifier in "category/platform" format
        actor: Individual user identity (user_id) of the approving admin
        audit_log: DevModeAuditLog instance (exposes .log_action)
        modules_dir: Base modules directory (str or Path)
        org_id: Tenant organization id, preserved in audit details now that
            `actor` identifies the individual admin, not the org (WR-02)

    Returns:
        Dict with status, module_id, new_status (on success) or error
    """
    manifest_path = _resolve_manifest_path(module_id, modules_dir)
    if not manifest_path.exists():
        return {"status": "error", "error": f"Module not found: {module_id}"}

    manifest = ModuleManifest.load(manifest_path)

    if manifest.status != ModuleStatus.VALIDATED and manifest.status != ModuleStatus.VALIDATED.value:
        return {
            "status": "error",
            "error": (
                f"Module {module_id} cannot be approved from status "
                f"'{manifest.status}'. Only VALIDATED modules may be approved."
            ),
        }

    # Compute the code-bundle hash BEFORE the status mutation so it reflects
    # exactly what the admin reviewed (manifest.json is excluded, so the
    # subsequent status/updated_at rewrite below does not invalidate it).
    bundle_sha256 = _bundle_hash(module_id, modules_dir)

    manifest.status = ModuleStatus.APPROVED
    manifest.approved_bundle_sha256 = bundle_sha256 or ""
    manifest.save(Path(modules_dir))

    timestamp = datetime.now(timezone.utc).isoformat()
    audit_log.log_action(
        action="module_approved",
        actor=actor,
        module_id=module_id,
        details={"bundle_sha256": bundle_sha256, "timestamp": timestamp, "org_id": org_id},
    )

    logger.info(f"Module approved: {module_id} by {actor}")

    return {
        "status": "success",
        "module_id": module_id,
        "new_status": ModuleStatus.APPROVED.value,
        "bundle_sha256": bundle_sha256,
    }


def reject_module(
    module_id: str,
    feedback: Optional[str],
    actor: str,
    audit_log: Any,
    modules_dir: Union[str, Path],
    org_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reject a module (D-09/D-10/D-19).

    - Non-empty feedback: bounded repair cycle. Status moves to VALIDATING;
      one repair_module() attempt is triggered using the feedback as a
      repair hint. A subsequent validate_module() call is expected to move
      the module back to VALIDATED for re-review.
    - Empty/None feedback: terminal rejection. Status becomes FAILED and the
      module's heavyweight artifacts are queued for GC via queue_for_gc()
      (D-10).

    Every decision is recorded via audit_log.log_action with actor,
    timestamp, bundle hash, and a terminal flag (D-19).

    Args:
        module_id: Module identifier in "category/platform" format
        feedback: Reviewer feedback text driving a repair cycle, or
            empty/None for a terminal rejection
        actor: Individual user identity (user_id) of the rejecting admin
        audit_log: DevModeAuditLog instance (exposes .log_action)
        modules_dir: Base modules directory (str or Path)
        org_id: Tenant organization id, preserved in audit details now that
            `actor` identifies the individual admin, not the org (WR-02)

    Returns:
        Dict with status, module_id, new_status (on success) or error
    """
    manifest_path = _resolve_manifest_path(module_id, modules_dir)
    if not manifest_path.exists():
        return {"status": "error", "error": f"Module not found: {module_id}"}

    manifest = ModuleManifest.load(manifest_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    bundle_sha256 = _bundle_hash(module_id, modules_dir)

    if feedback:
        manifest.status = ModuleStatus.VALIDATING
        manifest.save(Path(modules_dir))

        # Best-effort bounded repair cycle (D-09). Failures here (e.g. no
        # LLM gateway wired, missing generated build artifacts) must not
        # block the reject decision itself — repair is fire-and-forget from
        # this function's perspective; the module remains in VALIDATING
        # pending an explicit re-validate_module() call either way.
        try:
            from shared.modules.audit import BuildAuditLog
            from tools.builtin.module_builder import repair_module

            repair_job_id = (
                f"reject_repair_{module_id.replace('/', '_')}_"
                f"{int(datetime.now(timezone.utc).timestamp())}"
            )
            repair_audit_log = BuildAuditLog(job_id=repair_job_id, module_id=module_id)
            validation_report = {
                "fix_hints": [
                    {"category": "reviewer_feedback", "message": feedback},
                ],
            }
            repair_module(module_id, validation_report, repair_audit_log)
        except Exception as e:
            logger.warning(f"Repair cycle for {module_id} could not be completed: {e}")

        audit_log.log_action(
            action="module_rejected",
            actor=actor,
            module_id=module_id,
            details={
                "bundle_sha256": bundle_sha256,
                "timestamp": timestamp,
                "terminal": False,
                "feedback": feedback,
                "org_id": org_id,
            },
        )

        logger.info(f"Module rejected with feedback (repair cycle): {module_id} by {actor}")

        return {
            "status": "success",
            "module_id": module_id,
            "new_status": ModuleStatus.VALIDATING.value,
        }

    # Terminal rejection — no feedback provided (D-09/D-10)
    manifest.status = ModuleStatus.FAILED
    manifest.save(Path(modules_dir))

    queue_for_gc(module_id, modules_dir, actor=actor)

    audit_log.log_action(
        action="module_rejected",
        actor=actor,
        module_id=module_id,
        details={
            "bundle_sha256": bundle_sha256,
            "timestamp": timestamp,
            "terminal": True,
            "org_id": org_id,
        },
    )

    logger.info(f"Module rejected (terminal): {module_id} by {actor}")

    return {
        "status": "success",
        "module_id": module_id,
        "new_status": ModuleStatus.FAILED.value,
    }
