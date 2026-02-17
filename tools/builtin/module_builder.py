"""
Module Builder Tool — LLM-driven module generation with stage pipeline.

Generation flow:
    1. Scaffold stage: Create directory, manifest, stub adapter, base tests
    2. Implement stage: Call LLM gateway to generate adapter.py implementation
    3. Tests stage: Call LLM gateway to generate test_adapter.py
    4. Repair stage (if validation fails): Call LLM gateway with fix hints to repair

Features:
    - Stage-based pipeline with deterministic artifact tracking
    - Bounded repair loop (max 10 attempts) with failure fingerprinting
    - Immutable attempt records with audit trail
    - Terminal failure detection (policy/security violations stop immediately)
"""
import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

from shared.modules.manifest import ModuleManifest, ModuleStatus, ValidationResults
from shared.modules.templates.adapter_template import generate_adapter_code
from shared.modules.templates.test_template import generate_test_code
from shared.modules.artifacts import ArtifactBundleBuilder, ArtifactIndex
from shared.modules.identifiers import parse_module_id
from shared.modules.hashing import compute_sha256
from shared.modules.audit import (
    BuildAuditLog,
    AttemptRecord,
    AttemptStatus,
    FailureType,
    FailureFingerprint,
)
from shared.modules.contracts import GeneratorResponseContract
from shared.providers.llm_gateway import (
    LLMGateway,
    Purpose,
    BudgetExceededError,
    SchemaValidationError,
    AllModelsFailedError,
)
from shared.providers.base_provider import ChatMessage
from shared.agents.prompt_composer import compose, StageContext, load_soul
from shared.agents.confidence import Blueprint2CodeScorer

logger = logging.getLogger(__name__)

MODULES_DIR = Path(os.getenv("MODULES_DIR", "/app/modules"))
AUDIT_DIR = Path(os.getenv("AUDIT_DIR", "/app/data/audit"))

# Configuration
MAX_REPAIR_ATTEMPTS = 10

# Global gateway reference (set by orchestrator)
_llm_gateway: Optional[LLMGateway] = None

# Load builder soul and create confidence scorer at module level
_builder_soul = load_soul("builder")
_scorer = Blueprint2CodeScorer(threshold=0.6)


def set_llm_gateway(gateway: LLMGateway) -> None:
    """Wire LLM gateway from orchestrator."""
    global _llm_gateway
    _llm_gateway = gateway


REPAIR_SYSTEM_PROMPT = """\
You are a Python adapter code repair agent for the NEXUS module system.

Your task is to fix failing adapter code based on validation errors and fix hints.

Rules:
- Return ONLY valid JSON conforming to the GeneratorResponseContract schema.
- Each changed_file must have a "path" and "content" field.
- File content must NOT contain markdown fences (``` or similar).
- Never use forbidden imports: subprocess, os.system, shutil.rmtree, eval, exec, __import__.
- Every adapter must have: @register_adapter decorator, fetch_raw(), transform(), get_schema() methods.
- Keep fixes minimal — only change what's needed to pass validation.
"""


def _build_repair_user_prompt(
    module_id: str,
    current_files: Dict[str, str],
    fix_hints_text: str,
    failing_logs: str,
) -> str:
    """Build the user prompt for repair with current code and errors."""
    parts = [f"## Module: {module_id}\n"]

    for filename, content in current_files.items():
        parts.append(f"## Current {filename}:\n{content}\n")

    parts.append(f"## Validation Failures:\n{fix_hints_text}\n")

    if failing_logs.strip():
        parts.append(f"## Test Output (truncated):\n{failing_logs[:2000]}\n")

    parts.append(
        "## Task:\n"
        "Fix the code to pass all validations. Return the corrected files "
        "using the GeneratorResponseContract JSON schema."
    )

    return "\n".join(parts)


def _run_async(coro):
    """Run async coroutine from sync context, handling existing event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)

    # Event loop already running — use thread to avoid nested loop
    result = [None]
    exception = [None]

    def _target():
        try:
            result[0] = asyncio.run(coro)
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join(timeout=120)

    if exception[0] is not None:
        raise exception[0]
    return result[0]


@dataclass
class BuildSession:
    """
    Tracks state for a single module build job.

    Provides idempotent job identity via normalized request hash.
    Tracks current stage, attempt number, and artifact references.
    """
    job_id: str
    module_id: str
    current_stage: str = "scaffold"
    attempt_number: int = 0
    artifacts: List[ArtifactIndex] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z")

    @classmethod
    def create_job_id(cls, module_id: str, spec: Dict[str, Any]) -> str:
        """Create deterministic job ID from module ID and spec."""
        spec_json = json.dumps(spec, sort_keys=True)
        spec_hash = compute_sha256(spec_json.encode())[:8]
        return f"{module_id.replace('/', '_')}_{spec_hash}"


def build_module(
    name: str,
    category: str,
    platform: str = "",
    description: str = "",
    api_base_url: str = "https://api.example.com/v1",
    requires_api_key: bool = True,
    auth_type: str = "api_key",
    icon: str = "🔌",
    display_name: str = "",
) -> Dict[str, Any]:
    """
    Create a new adapter module using LLM-driven stage pipeline.

    Stage pipeline:
        1. Scaffold: Create directory, manifest, stub files
        2. Implement: LLM generates adapter.py
        3. Tests: LLM generates test_adapter.py
        4. Validate: Run tests in sandbox
        5. Repair (if needed): LLM fixes issues based on validation report

    Args:
        name: Module name (e.g., "clashroyale")
        category: Module category (e.g., "gaming", "health", "finance")
        platform: Platform identifier (defaults to name)
        description: Human-readable description
        api_base_url: Base URL of the API to integrate
        requires_api_key: Whether API needs authentication
        auth_type: Authentication type ("api_key", "oauth2", "basic", "none")
        icon: Emoji icon for the module
        display_name: Human-readable display name

    Returns:
        Dict with status, module_id, stage info, and artifacts
    """
    if not platform:
        platform = name

    if not display_name:
        display_name = name.replace("_", " ").title()

    module_id = f"{category}/{platform}"
    module_dir = MODULES_DIR / category / platform

    # Check if module already exists
    if module_dir.exists() and (module_dir / "manifest.json").exists():
        return {
            "status": "error",
            "error": f"Module {module_id} already exists. Use write_module_code() to update it.",
            "module_id": module_id,
        }

    # Create build session
    spec = {
        "name": name,
        "category": category,
        "platform": platform,
        "description": description,
        "api_base_url": api_base_url,
        "requires_api_key": requires_api_key,
        "auth_type": auth_type,
    }
    session = BuildSession(
        job_id=BuildSession.create_job_id(module_id, spec),
        module_id=module_id,
        current_stage="scaffold"
    )

    # ========== SCAFFOLD STAGE ==========
    logger.info(f"[{session.job_id}] Starting scaffold stage for {module_id}")

    manifest = ModuleManifest(
        name=name,
        category=category,
        platform=platform,
        display_name=display_name,
        description=description,
        icon=icon,
        requires_api_key=requires_api_key,
        auth_type=auth_type,
        status=ModuleStatus.PENDING,
        created_by="executor_agent",
    )

    # Generate adapter code skeleton
    adapter_code = generate_adapter_code(
        module_name=name,
        category=category,
        platform=platform,
        display_name=display_name,
        description=description,
        icon=icon,
        class_name=manifest.class_name,
        requires_auth=requires_api_key,
        auth_type=auth_type,
        api_base_url=api_base_url,
    )

    # Generate test code
    test_code = generate_test_code(
        class_name=manifest.class_name,
        module_name=name,
        category=category,
        platform=platform,
        requires_auth=requires_api_key,
        api_base_url=api_base_url,
    )

    # Write files
    module_dir.mkdir(parents=True, exist_ok=True)
    manifest.save(MODULES_DIR)
    manifest_file = module_dir / "manifest.json"
    (module_dir / "adapter.py").write_text(adapter_code)
    (module_dir / "test_adapter.py").write_text(test_code)

    # Create artifact bundle for scaffold stage
    scaffold_files = {
        f"{category}/{platform}/manifest.json": manifest_file.read_text(),
        f"{category}/{platform}/adapter.py": adapter_code,
        f"{category}/{platform}/test_adapter.py": test_code,
    }

    artifact_index = ArtifactBundleBuilder.build_from_dict(
        files=scaffold_files,
        job_id=session.job_id,
        attempt_id=session.attempt_number,
        module_id=module_id,
        stage="scaffold"
    )
    session.artifacts.append(artifact_index)
    session.attempt_number += 1

    logger.info(f"[{session.job_id}] Scaffold stage complete: {artifact_index.bundle_sha256}")

    return {
        "status": "success",
        "module_id": module_id,
        "job_id": session.job_id,
        "stage": "scaffold",
        "adapter_code": adapter_code,
        "module_dir": str(module_dir),
        "files_created": [
            str(module_dir / "manifest.json"),
            str(module_dir / "adapter.py"),
            str(module_dir / "test_adapter.py"),
        ],
        "class_name": manifest.class_name,
        "artifact_bundle": artifact_index.bundle_sha256,
        "instructions": (
            f"Module skeleton created at {module_dir}. "
            f"The adapter.py contains a default fetch/transform implementation. "
            f"Customize the fetch_raw() and transform() methods for the "
            f"{display_name} API, then call write_module_code() with the "
            f"updated code, and validate_module() to test it."
        ),
    }


def write_module_code(
    module_id: str,
    adapter_code: str,
    test_code: str = "",
) -> Dict[str, Any]:
    """
    Write or update the adapter code for an existing module.

    Use this after build_module() to write the LLM-generated
    API-specific adapter logic. The module_id is "{category}/{platform}".

    Args:
        module_id: Module identifier in "category/platform" format
        adapter_code: Complete Python source code for adapter.py
        test_code: Optional updated test code

    Returns:
        Dict with status and file paths written
    """
    try:
        parsed = parse_module_id(module_id)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    category, platform = parsed.category, parsed.platform
    module_dir = MODULES_DIR / category / platform

    if not module_dir.exists():
        return {"status": "error", "error": f"Module directory not found: {module_dir}. Call build_module() first."}

    # Syntax check before writing
    try:
        compile(adapter_code, f"{module_id}/adapter.py", "exec")
    except SyntaxError as e:
        return {
            "status": "error",
            "error": f"Syntax error in adapter code: {e}",
            "line": e.lineno,
            "offset": e.offset,
        }

    # Write adapter
    (module_dir / "adapter.py").write_text(adapter_code)
    files_written = [str(module_dir / "adapter.py")]

    # Write tests if provided
    if test_code:
        try:
            compile(test_code, f"{module_id}/test_adapter.py", "exec")
        except SyntaxError as e:
            return {
                "status": "error",
                "error": f"Syntax error in test code: {e}",
                "line": e.lineno,
            }
        (module_dir / "test_adapter.py").write_text(test_code)
        files_written.append(str(module_dir / "test_adapter.py"))

    # Update manifest status
    manifest_path = module_dir / "manifest.json"
    if manifest_path.exists():
        manifest = ModuleManifest.load(manifest_path)
        manifest.status = ModuleStatus.PENDING
        manifest.save(MODULES_DIR)

    logger.info(f"Module code written: {module_id}")

    return {
        "status": "success",
        "module_id": module_id,
        "files_written": files_written,
        "instructions": f"Code written. Call validate_module('{module_id}') to test it.",
    }


def repair_module(
    module_id: str,
    validation_report: Dict[str, Any],
    audit_log: BuildAuditLog,
) -> Dict[str, Any]:
    """
    Repair module using LLM with bounded retry loop.

    Repair loop:
        1. Extract fix hints from validation report
        2. Load current file snapshots (no stale context)
        3. Call LLM gateway with purpose=REPAIR
        4. Apply patches to changed files
        5. Create artifact bundle
        6. Record immutable attempt
        7. Check termination conditions:
           - Terminal failure (policy/security) → stop immediately
           - Max attempts reached → stop with failure report
           - Identical failure fingerprint twice → stop (thrash detection)
           - Otherwise → continue

    Args:
        module_id: Module identifier in "category/platform" format
        validation_report: Validation report with fix hints
        audit_log: Build audit log for tracking attempts

    Returns:
        Dict with repair status, updated files, and next steps
    """
    try:
        parsed = parse_module_id(module_id)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    category, platform = parsed.category, parsed.platform
    module_dir = MODULES_DIR / category / platform

    if not module_dir.exists():
        return {"status": "error", "error": f"Module not found: {module_dir}"}

    # Check if we've exceeded max attempts
    if len(audit_log.attempts) >= MAX_REPAIR_ATTEMPTS:
        return {
            "status": "failed",
            "error": f"Max repair attempts ({MAX_REPAIR_ATTEMPTS}) reached",
            "audit_log": audit_log.to_dict(),
        }

    # Classify failure type
    failure_type = audit_log.classify_failure_type(validation_report)

    # Terminal failures stop immediately
    if failure_type in [
        FailureType.POLICY_VIOLATION,
        FailureType.SECURITY_BLOCK,
        FailureType.BUDGET_EXCEEDED,
        FailureType.GATEWAY_FAILURE,
    ]:
        logger.error(
            f"[{audit_log.job_id}] Terminal failure detected: {failure_type.value}"
        )
        return {
            "status": "failed",
            "error": f"Terminal failure: {failure_type.value}. Cannot repair.",
            "failure_type": failure_type.value,
            "audit_log": audit_log.to_dict(),
        }

    # Check for thrashing (identical failure twice)
    if audit_log.has_consecutive_identical_failures():
        logger.warning(
            f"[{audit_log.job_id}] Thrashing detected: identical failure fingerprint twice"
        )
        return {
            "status": "failed",
            "error": "Thrashing detected: same failure repeated. Stopping repair loop.",
            "audit_log": audit_log.to_dict(),
        }

    # Create failure fingerprint
    fingerprint = FailureFingerprint.from_validation_report(validation_report)

    # Load current file snapshots (fresh context, no stale data)
    adapter_file = module_dir / "adapter.py"
    test_file = module_dir / "test_adapter.py"

    current_files = {}
    if adapter_file.exists():
        current_files["adapter.py"] = adapter_file.read_text()
    if test_file.exists():
        current_files["test_adapter.py"] = test_file.read_text()

    # Extract fix hints
    fix_hints = validation_report.get("fix_hints", [])
    fix_hints_text = "\n".join([
        f"- {hint.get('category', 'unknown')}: {hint.get('message', '')}"
        for hint in fix_hints
    ])

    # Get failing logs
    runtime_results = validation_report.get("runtime_results", {})
    failing_logs = runtime_results.get("stderr", "") + "\n" + runtime_results.get("stdout", "")

    logger.info(
        f"[{audit_log.job_id}] Starting repair attempt {len(audit_log.attempts) + 1}"
    )

    # Call LLM gateway with repair prompt
    if _llm_gateway is None:
        # No gateway available — record pending and return instructions
        attempt_record = AttemptRecord(
            attempt_number=len(audit_log.attempts) + 1,
            bundle_sha256="pending",
            stage="repair",
            status=AttemptStatus.FAILED,
            validation_report=validation_report,
            logs=[f"Fix hints: {fix_hints_text}", f"Failing logs: {failing_logs[:500]}"],
            failure_fingerprint=fingerprint.hash,
            failure_type=failure_type,
            metadata={"current_files": list(current_files.keys())},
        )
        audit_log.add_attempt(attempt_record)
        audit_file = audit_log.save(AUDIT_DIR)
        return {
            "status": "repair_pending",
            "module_id": module_id,
            "attempt_number": attempt_record.attempt_number,
            "failure_type": failure_type.value,
            "fingerprint": fingerprint.hash,
            "fix_hints": fix_hints,
            "audit_file": str(audit_file),
            "instructions": (
                f"Repair attempt {attempt_record.attempt_number} recorded. "
                f"LLM gateway not available. Fix hints: {fix_hints_text}"
            ),
        }

    # Build repair prompt using auto-composition
    # Create stage context with repair hints
    stage_context = StageContext(
        stage="repair",
        attempt=len(audit_log.attempts) + 1,
        intent=f"Repair module {module_id} based on validation failures",
        repair_hints=[
            f"{hint.get('category', 'unknown')}: {hint.get('message', '')}"
            for hint in fix_hints
        ],
        prior_artifacts={"current_files": current_files},
        policy_profile="default",
    )

    # Compose system prompt from builder soul + stage context
    system_prompt = compose(
        system=_builder_soul,
        context=stage_context,
        output_schema=GeneratorResponseContract.model_json_schema(),
    )

    # Build user message with current files and errors
    user_message = _build_repair_user_prompt(
        module_id, current_files, fix_hints_text, failing_logs,
    )

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_message),
    ]

    contract_schema = GeneratorResponseContract.model_json_schema()
    allowed_dirs = [f"modules/{category}/{platform}", f"{category}/{platform}"]

    try:
        contract, gen_metadata = _run_async(
            _llm_gateway.generate(
                purpose=Purpose.REPAIR,
                messages=messages,
                schema=contract_schema,
                allowed_dirs=allowed_dirs,
                job_id=audit_log.job_id,
                temperature=0.4,
            )
        )

        # Apply patches from generated contract
        for file_change in contract.changed_files:
            target = module_dir / Path(file_change.path).name
            target.write_text(file_change.content)

        # Build artifact bundle from updated files
        updated_files = {}
        for fn in ["adapter.py", "test_adapter.py", "manifest.json"]:
            fp = module_dir / fn
            if fp.exists():
                updated_files[f"{category}/{platform}/{fn}"] = fp.read_text()

        bundle = ArtifactBundleBuilder.build_from_dict(
            files=updated_files,
            job_id=audit_log.job_id,
            attempt_id=len(audit_log.attempts) + 1,
            module_id=module_id,
        )

        # Record success attempt
        attempt_record = AttemptRecord(
            attempt_number=len(audit_log.attempts) + 1,
            bundle_sha256=bundle.bundle_sha256,
            stage="repair",
            status=AttemptStatus.SUCCESS,
            validation_report=validation_report,
            logs=[
                f"Fix hints: {fix_hints_text}",
                f"Changed files: {[fc.path for fc in contract.changed_files]}",
                f"Provider: {gen_metadata.get('provider', 'unknown')}",
            ],
            failure_fingerprint=fingerprint.hash,
            failure_type=failure_type,
            metadata={
                "changed_files": [fc.path for fc in contract.changed_files],
                "provider": gen_metadata.get("provider"),
                "model": gen_metadata.get("model"),
            },
        )
        audit_log.add_attempt(attempt_record)
        audit_file = audit_log.save(AUDIT_DIR)

        logger.info(
            f"[{audit_log.job_id}] Repair attempt {attempt_record.attempt_number} "
            f"succeeded — {len(contract.changed_files)} files patched"
        )

        return {
            "status": "success",
            "module_id": module_id,
            "attempt_number": attempt_record.attempt_number,
            "bundle_sha256": bundle.bundle_sha256,
            "changed_files": [fc.path for fc in contract.changed_files],
            "audit_file": str(audit_file),
            "instructions": (
                f"Repair applied ({len(contract.changed_files)} files). "
                f"Call validate_module('{module_id}') to verify."
            ),
        }

    except (BudgetExceededError, SchemaValidationError, AllModelsFailedError) as e:
        logger.error(
            f"[{audit_log.job_id}] Repair gateway call failed: {type(e).__name__}: {e}"
        )

        attempt_record = AttemptRecord(
            attempt_number=len(audit_log.attempts) + 1,
            bundle_sha256="error",
            stage="repair",
            status=AttemptStatus.FAILED,
            validation_report=validation_report,
            logs=[f"Gateway error: {type(e).__name__}: {e}"],
            failure_fingerprint=fingerprint.hash,
            failure_type=FailureType.GATEWAY_FAILURE,
            metadata={"error_type": type(e).__name__, "error_message": str(e)},
        )
        audit_log.add_attempt(attempt_record)
        audit_file = audit_log.save(AUDIT_DIR)

        return {
            "status": "failed",
            "module_id": module_id,
            "attempt_number": attempt_record.attempt_number,
            "failure_type": FailureType.GATEWAY_FAILURE.value,
            "fingerprint": fingerprint.hash,
            "error": str(e),
            "audit_file": str(audit_file),
        }
