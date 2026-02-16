"""
Draft lifecycle management for dev-mode module editing.

Enables safe human edits with full audit trail:
- Create draft from installed module
- Edit files in isolated workspace
- View diffs against source version
- Discard drafts when no longer needed

Drafts are never directly installable — they must go through
validate_draft() -> promote_draft() -> install_module() flow
to preserve supply-chain integrity.
"""
import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class DraftState(str, Enum):
    """Draft lifecycle states."""
    CREATED = "created"
    EDITING = "editing"
    VALIDATING = "validating"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    DISCARDED = "discarded"


@dataclass
class DraftMetadata:
    """
    Metadata for a draft module.

    Attributes:
        draft_id: Unique draft identifier
        module_id: Source module identifier (category/platform)
        source_version: Version reference of source module
        state: Current draft state
        created_at: ISO timestamp of draft creation
        created_by: Actor who created the draft
        updated_at: ISO timestamp of last modification
        updated_by: Actor who last modified the draft
        files: Dict of file paths to content hashes
        validation_report: Last validation report (if validated)
    """
    draft_id: str
    module_id: str
    source_version: str
    state: DraftState
    created_at: str
    created_by: str
    updated_at: str = ""
    updated_by: str = ""
    files: Dict[str, str] = field(default_factory=dict)  # filename -> sha256
    validation_report: Optional[Dict[str, Any]] = None
    bundle_sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert enums to values
        if isinstance(data.get("state"), Enum):
            data["state"] = data["state"].value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftMetadata":
        """Create DraftMetadata from dictionary."""
        if "state" in data and isinstance(data["state"], str):
            data["state"] = DraftState(data["state"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DraftManager:
    """
    Manages draft lifecycle for dev-mode module editing.

    Draft workspace structure:
        data/drafts/{draft_id}/
            metadata.json
            files/
                adapter.py
                test_adapter.py
                manifest.json
    """

    def __init__(self, drafts_dir: Path, modules_dir: Path, audit_log=None):
        """
        Initialize draft manager.

        Args:
            drafts_dir: Directory for draft workspaces
            modules_dir: Directory for installed modules
            audit_log: Audit log instance for recording actions
        """
        self.drafts_dir = Path(drafts_dir)
        self.modules_dir = Path(modules_dir)
        self.audit_log = audit_log
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

    def create_draft(
        self,
        module_id: str,
        from_version: str = "active",
        actor: str = "system"
    ) -> Dict[str, Any]:
        """
        Create a draft from an installed module.

        Copies installed module files into isolated draft workspace,
        preserving source version reference for diff generation.

        Args:
            module_id: Module identifier (category/platform)
            from_version: Version reference (default: "active")
            actor: Identity of the user creating the draft

        Returns:
            Dict with draft_id, status, and draft metadata
        """
        parts = module_id.split("/")
        if len(parts) != 2:
            return {"status": "error", "error": f"Invalid module_id: {module_id}"}

        category, platform = parts
        module_dir = self.modules_dir / category / platform

        if not module_dir.exists():
            return {
                "status": "error",
                "error": f"Module {module_id} not found. Install it first."
            }

        # Generate draft ID
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        draft_id = f"{module_id.replace('/', '_')}_{timestamp}"

        draft_workspace = self.drafts_dir / draft_id
        draft_files_dir = draft_workspace / "files"
        draft_files_dir.mkdir(parents=True, exist_ok=True)

        # Copy module files
        files_copied = {}
        for filename in ["adapter.py", "test_adapter.py", "manifest.json"]:
            src_file = module_dir / filename
            if src_file.exists():
                dest_file = draft_files_dir / filename
                shutil.copy2(src_file, dest_file)
                content = dest_file.read_text()
                file_hash = hashlib.sha256(content.encode()).hexdigest()
                files_copied[filename] = file_hash

        # Create metadata
        now = datetime.now(timezone.utc).isoformat() + "Z"
        metadata = DraftMetadata(
            draft_id=draft_id,
            module_id=module_id,
            source_version=from_version,
            state=DraftState.CREATED,
            created_at=now,
            created_by=actor,
            updated_at=now,
            updated_by=actor,
            files=files_copied
        )

        # Save metadata
        metadata_file = draft_workspace / "metadata.json"
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Audit log
        if self.audit_log:
            self.audit_log.log_action(
                action="draft_created",
                actor=actor,
                module_id=module_id,
                draft_id=draft_id,
                details={
                    "source_version": from_version,
                    "files_copied": list(files_copied.keys())
                }
            )

        logger.info(f"Draft created: {draft_id} from {module_id} (version: {from_version})")

        return {
            "status": "success",
            "draft_id": draft_id,
            "module_id": module_id,
            "source_version": from_version,
            "files": list(files_copied.keys()),
            "message": f"Draft {draft_id} created from {module_id}"
        }

    def edit_file(
        self,
        draft_id: str,
        file_path: str,
        content: str,
        actor: str = "system"
    ) -> Dict[str, Any]:
        """
        Edit a file in the draft workspace.

        Args:
            draft_id: Draft identifier
            file_path: File name to edit (adapter.py, test_adapter.py, manifest.json)
            content: New file content
            actor: Identity of the user making the edit

        Returns:
            Dict with status and updated metadata
        """
        draft_workspace = self.drafts_dir / draft_id
        metadata_file = draft_workspace / "metadata.json"

        if not metadata_file.exists():
            return {"status": "error", "error": f"Draft {draft_id} not found"}

        # Load metadata
        metadata = DraftMetadata.from_dict(json.loads(metadata_file.read_text()))

        # Check state
        if metadata.state in [DraftState.PROMOTED, DraftState.DISCARDED]:
            return {
                "status": "error",
                "error": f"Cannot edit draft in state: {metadata.state}"
            }

        # Validate file path
        allowed_files = ["adapter.py", "test_adapter.py", "manifest.json"]
        if file_path not in allowed_files:
            return {
                "status": "error",
                "error": f"Invalid file path. Allowed: {allowed_files}"
            }

        # Write file
        draft_file = draft_workspace / "files" / file_path
        draft_file.write_text(content)

        # Update metadata
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        metadata.files[file_path] = file_hash
        metadata.state = DraftState.EDITING
        metadata.updated_at = datetime.now(timezone.utc).isoformat() + "Z"
        metadata.updated_by = actor

        # Save metadata
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Audit log
        if self.audit_log:
            self.audit_log.log_action(
                action="draft_edited",
                actor=actor,
                draft_id=draft_id,
                details={
                    "file": file_path,
                    "file_hash": file_hash
                }
            )

        logger.info(f"Draft edited: {draft_id}, file: {file_path}")

        return {
            "status": "success",
            "draft_id": draft_id,
            "file": file_path,
            "file_hash": file_hash,
            "message": f"File {file_path} updated in draft {draft_id}"
        }

    def get_diff(self, draft_id: str, actor: str = "system") -> Dict[str, Any]:
        """
        Generate unified diff between draft and source version.

        Args:
            draft_id: Draft identifier
            actor: Identity of the user requesting diff

        Returns:
            Dict with diff content for each modified file
        """
        import difflib

        draft_workspace = self.drafts_dir / draft_id
        metadata_file = draft_workspace / "metadata.json"

        if not metadata_file.exists():
            return {"status": "error", "error": f"Draft {draft_id} not found"}

        # Load metadata
        metadata = DraftMetadata.from_dict(json.loads(metadata_file.read_text()))

        # Get source module directory
        parts = metadata.module_id.split("/")
        category, platform = parts
        source_dir = self.modules_dir / category / platform

        if not source_dir.exists():
            return {
                "status": "error",
                "error": f"Source module {metadata.module_id} no longer exists"
            }

        # Generate diffs
        diffs = {}
        draft_files_dir = draft_workspace / "files"

        for filename in metadata.files.keys():
            source_file = source_dir / filename
            draft_file = draft_files_dir / filename

            if not source_file.exists():
                diffs[filename] = f"File {filename} is new in draft (not in source)"
                continue

            source_lines = source_file.read_text().splitlines(keepends=True)
            draft_lines = draft_file.read_text().splitlines(keepends=True)

            diff = difflib.unified_diff(
                source_lines,
                draft_lines,
                fromfile=f"{metadata.module_id}/{filename} (source)",
                tofile=f"{metadata.module_id}/{filename} (draft)",
                lineterm=""
            )

            diff_text = "\n".join(diff)
            diffs[filename] = diff_text if diff_text else "No changes"

        # Audit log
        if self.audit_log:
            self.audit_log.log_action(
                action="draft_diff_viewed",
                actor=actor,
                draft_id=draft_id,
                details={"files": list(diffs.keys())}
            )

        return {
            "status": "success",
            "draft_id": draft_id,
            "module_id": metadata.module_id,
            "source_version": metadata.source_version,
            "diffs": diffs
        }

    def discard_draft(self, draft_id: str, actor: str = "system") -> Dict[str, Any]:
        """
        Mark a draft as discarded.

        Draft files are preserved for audit purposes but marked as discarded.

        Args:
            draft_id: Draft identifier
            actor: Identity of the user discarding the draft

        Returns:
            Dict with status
        """
        draft_workspace = self.drafts_dir / draft_id
        metadata_file = draft_workspace / "metadata.json"

        if not metadata_file.exists():
            return {"status": "error", "error": f"Draft {draft_id} not found"}

        # Load and update metadata
        metadata = DraftMetadata.from_dict(json.loads(metadata_file.read_text()))
        metadata.state = DraftState.DISCARDED
        metadata.updated_at = datetime.now(timezone.utc).isoformat() + "Z"
        metadata.updated_by = actor

        # Save metadata
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Audit log
        if self.audit_log:
            self.audit_log.log_action(
                action="draft_discarded",
                actor=actor,
                draft_id=draft_id,
                details={"module_id": metadata.module_id}
            )

        logger.info(f"Draft discarded: {draft_id}")

        return {
            "status": "success",
            "draft_id": draft_id,
            "message": f"Draft {draft_id} discarded (files preserved for audit)"
        }

    def get_draft(self, draft_id: str) -> Optional[DraftMetadata]:
        """
        Get draft metadata.

        Args:
            draft_id: Draft identifier

        Returns:
            DraftMetadata or None if not found
        """
        metadata_file = self.drafts_dir / draft_id / "metadata.json"
        if not metadata_file.exists():
            return None

        return DraftMetadata.from_dict(json.loads(metadata_file.read_text()))

    def list_drafts(self, module_id: Optional[str] = None) -> List[DraftMetadata]:
        """
        List all drafts, optionally filtered by module_id.

        Args:
            module_id: Optional module identifier to filter by

        Returns:
            List of DraftMetadata
        """
        drafts = []
        for draft_dir in self.drafts_dir.iterdir():
            if not draft_dir.is_dir():
                continue

            metadata_file = draft_dir / "metadata.json"
            if not metadata_file.exists():
                continue

            metadata = DraftMetadata.from_dict(json.loads(metadata_file.read_text()))

            if module_id is None or metadata.module_id == module_id:
                drafts.append(metadata)

        return sorted(drafts, key=lambda d: d.created_at, reverse=True)

    def validate_draft(
        self,
        draft_id: str,
        actor: str = "system",
        validator_func=None
    ) -> Dict[str, Any]:
        """
        Validate a draft using sandbox validation.

        Runs draft files through the same validation pipeline as automated builds:
        - Static checks (syntax, contract, manifest)
        - Runtime checks (tests in sandbox)
        - Generates ValidationReport with fix hints
        - Stores bundle_sha256 for promotion attestation

        Args:
            draft_id: Draft identifier
            actor: Identity of the user triggering validation
            validator_func: Optional validator function (for testing)

        Returns:
            Dict with validation report and updated draft status
        """
        draft_workspace = self.drafts_dir / draft_id
        metadata_file = draft_workspace / "metadata.json"

        if not metadata_file.exists():
            return {"status": "error", "error": f"Draft {draft_id} not found"}

        # Load metadata
        metadata = DraftMetadata.from_dict(json.loads(metadata_file.read_text()))

        # Check state
        if metadata.state in [DraftState.PROMOTED, DraftState.DISCARDED]:
            return {
                "status": "error",
                "error": f"Cannot validate draft in state: {metadata.state}"
            }

        # Update state to VALIDATING
        metadata.state = DraftState.VALIDATING
        metadata.updated_at = datetime.now(timezone.utc).isoformat() + "Z"
        metadata.updated_by = actor
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Copy draft files to temporary module location for validation
        draft_files_dir = draft_workspace / "files"
        parts = metadata.module_id.split("/")
        category, platform = parts

        # Create temporary validation directory
        temp_module_dir = self.modules_dir / f"{category}_draft_{draft_id}" / platform
        temp_module_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Copy files
            for filename in metadata.files.keys():
                src = draft_files_dir / filename
                dest = temp_module_dir / filename
                shutil.copy2(src, dest)

            # Run validation
            if validator_func:
                # Use provided validator (for testing)
                validation_result = validator_func(f"{category}_draft_{draft_id}/{platform}")
            else:
                # Use real module_validator
                from tools.builtin.module_validator import validate_module
                validation_result = validate_module(f"{category}_draft_{draft_id}/{platform}")

            # Extract report
            report = validation_result.get("report", {})
            status = validation_result.get("status", "error")

            # Compute bundle hash
            from shared.modules.artifacts import ArtifactBundleBuilder
            bundle_files = {}
            for filename in metadata.files.keys():
                file_path = draft_files_dir / filename
                bundle_files[f"{category}/{platform}/{filename}"] = file_path.read_text()

            bundle = ArtifactBundleBuilder.build_from_dict(
                files=bundle_files,
                job_id=f"draft_{draft_id}",
                attempt_id=1,
                module_id=metadata.module_id
            )

            # Update metadata
            if status == "success":
                metadata.state = DraftState.VALIDATED
                metadata.validation_report = report
                metadata.bundle_sha256 = bundle.bundle_sha256
            else:
                metadata.state = DraftState.EDITING  # Back to editing on failure
                metadata.validation_report = report

            metadata.updated_at = datetime.now(timezone.utc).isoformat() + "Z"
            metadata.updated_by = actor
            metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

            # Audit log
            if self.audit_log:
                self.audit_log.log_action(
                    action="draft_validated",
                    actor=actor,
                    draft_id=draft_id,
                    details={
                        "validation_status": status,
                        "bundle_sha256": metadata.bundle_sha256
                    }
                )

            logger.info(f"Draft validated: {draft_id}, status: {status}")

            return {
                "status": "success" if status == "success" else "failed",
                "draft_id": draft_id,
                "validation_report": report,
                "bundle_sha256": metadata.bundle_sha256,
                "draft_state": metadata.state.value,
                "message": (
                    f"Draft {draft_id} validation passed. Ready for promotion."
                    if status == "success"
                    else f"Draft {draft_id} validation failed. Fix errors and validate again."
                )
            }

        finally:
            # Clean up temporary validation directory
            temp_parent = self.modules_dir / f"{category}_draft_{draft_id}"
            if temp_parent.exists():
                shutil.rmtree(temp_parent)

    def promote_draft(
        self,
        draft_id: str,
        actor: str = "system",
        installer_func=None
    ) -> Dict[str, Any]:
        """
        Promote a validated draft to a new immutable version.

        Creates a new validated version with:
        - New bundle_sha256 (computed during validation)
        - Validation attestation (from validation report)
        - Install via module_installer (same attestation guard)

        Pre-conditions:
        - Draft state must be VALIDATED
        - Validation report must exist
        - Bundle hash must exist

        Args:
            draft_id: Draft identifier
            actor: Identity of the user promoting the draft
            installer_func: Optional installer function (for testing)

        Returns:
            Dict with promotion status and new version info
        """
        draft_workspace = self.drafts_dir / draft_id
        metadata_file = draft_workspace / "metadata.json"

        if not metadata_file.exists():
            return {"status": "error", "error": f"Draft {draft_id} not found"}

        # Load metadata
        metadata = DraftMetadata.from_dict(json.loads(metadata_file.read_text()))

        # Check pre-conditions
        if metadata.state != DraftState.VALIDATED:
            return {
                "status": "error",
                "error": f"Draft must be VALIDATED before promotion. Current state: {metadata.state}"
            }

        if not metadata.validation_report:
            return {
                "status": "error",
                "error": "No validation report found. Run validate_draft() first."
            }

        if not metadata.bundle_sha256:
            return {
                "status": "error",
                "error": "No bundle hash found. Run validate_draft() first."
            }

        # Copy draft files to module directory
        parts = metadata.module_id.split("/")
        category, platform = parts
        module_dir = self.modules_dir / category / platform
        module_dir.mkdir(parents=True, exist_ok=True)

        draft_files_dir = draft_workspace / "files"
        for filename in metadata.files.keys():
            src = draft_files_dir / filename
            dest = module_dir / filename
            shutil.copy2(src, dest)

        # Create validation attestation
        attestation = {
            "bundle_sha256": metadata.bundle_sha256,
            "validated_at": metadata.validation_report.get("validated_at"),
            "validation_report": metadata.validation_report,
            "draft_id": draft_id,
            "promoted_by": actor,
            "promoted_at": datetime.now(timezone.utc).isoformat() + "Z"
        }

        # Install via module_installer
        if installer_func:
            # Use provided installer (for testing)
            install_result = installer_func(metadata.module_id, attestation)
        else:
            # Use real module_installer
            from tools.builtin.module_installer import install_module
            install_result = install_module(metadata.module_id, attestation)

        if install_result.get("status") != "success":
            return {
                "status": "error",
                "error": f"Installation failed: {install_result.get('error', 'unknown error')}",
                "install_result": install_result
            }

        # Update metadata
        metadata.state = DraftState.PROMOTED
        metadata.updated_at = datetime.now(timezone.utc).isoformat() + "Z"
        metadata.updated_by = actor
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Audit log
        if self.audit_log:
            self.audit_log.log_action(
                action="draft_promoted",
                actor=actor,
                draft_id=draft_id,
                module_id=metadata.module_id,
                details={
                    "bundle_sha256": metadata.bundle_sha256,
                    "source_version": metadata.source_version
                }
            )

        logger.info(f"Draft promoted: {draft_id} -> {metadata.module_id}")

        return {
            "status": "success",
            "draft_id": draft_id,
            "module_id": metadata.module_id,
            "bundle_sha256": metadata.bundle_sha256,
            "message": f"Draft {draft_id} promoted to {metadata.module_id}. Module installed with new version.",
            "install_result": install_result
        }
