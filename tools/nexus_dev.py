"""
NEXUS Dev Sandbox CLI — local development tool for the self-evolution pipeline.

Exercises the full module lifecycle without Docker/gRPC:
    build → validate → install (full pipeline)
    draft → edit → validate → promote → rollback (dev-mode lifecycle)

Usage:
    python -m tools.nexus_dev build weather/openweather
    python -m tools.nexus_dev validate weather/openweather
    python -m tools.nexus_dev draft create weather/openweather
    python -m tools.nexus_dev status
"""
import argparse
import importlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List, Optional

# Mock gRPC proto modules before any NEXUS imports
for _mod in ("llm_service", "llm_service.llm_pb2", "llm_service.llm_pb2_grpc"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from shared.modules.manifest import ModuleManifest, ModuleStatus
from shared.modules.artifacts import ArtifactBundleBuilder
from shared.modules.audit import DevModeAuditLog, BuildAuditLog
from shared.modules.drafts import DraftManager
from shared.modules.versioning import VersionManager
from shared.modules.contracts import GeneratorResponseContract, FileChange
from shared.modules.templates.adapter_template import generate_adapter_code
from shared.modules.templates.test_template import generate_test_code
from shared.providers.base_provider import (
    BaseProvider, ChatMessage, ChatRequest, ChatResponse, ModelInfo,
)
from shared.providers.llm_gateway import LLMGateway, RoutingPolicy, ModelPreference, BudgetConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nexus_dev")


class MockLLMProvider(BaseProvider):
    """Mock LLM provider that returns valid adapter code from templates."""

    def __init__(self):
        super().__init__(name="mock-dev")

    async def generate(self, request: ChatRequest) -> ChatResponse:
        """Return a canned GeneratorResponseContract-shaped JSON response."""
        # Extract module info from the prompt
        user_msg = next(
            (m.content for m in request.messages if m.role == "user"), ""
        )

        # Generate valid adapter code using existing templates
        adapter_code = generate_adapter_code(
            module_name="mock_adapter",
            category="dev",
            platform="sandbox",
            api_base_url="https://api.example.com/v1",
            auth_type="api_key",
        )
        test_code = generate_test_code(
            module_name="mock_adapter",
            category="dev",
            platform="sandbox",
        )

        contract = {
            "stage": "repair",
            "module": "dev/sandbox",
            "changed_files": [
                {"path": "dev/sandbox/adapter.py", "content": adapter_code},
                {"path": "dev/sandbox/test_adapter.py", "content": test_code},
            ],
            "deleted_files": [],
            "assumptions": ["Mock provider — using template code"],
            "rationale": "Template-based repair for dev sandbox",
            "policy": "adapter_contract_v1",
            "validation_report": {"self_check": "passed"},
        }

        return ChatResponse(
            content=json.dumps(contract),
            model="mock-dev",
            usage={"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        )

    async def list_models(self) -> List[ModelInfo]:
        return [ModelInfo(name="mock-dev", description="Mock provider for dev sandbox")]

    async def health_check(self) -> bool:
        return True


class DevSandbox:
    """
    Local development sandbox that wires NEXUS module system components
    without Docker, gRPC, or external services.
    """

    def __init__(self, workspace: Optional[Path] = None):
        self.workspace = workspace or Path.home() / ".nexus-dev"
        self._setup_workspace()
        self._wire_dependencies()
        logger.info(f"Dev sandbox initialized at {self.workspace}")

    def _setup_workspace(self):
        """Create workspace directories."""
        self.modules_dir = self.workspace / "modules"
        self.drafts_dir = self.workspace / "drafts"
        self.audit_dir = self.workspace / "audit"
        self.artifacts_dir = self.workspace / "artifacts"
        self.db_path = str(self.workspace / "module_versions.db")

        for d in [self.modules_dir, self.drafts_dir, self.audit_dir, self.artifacts_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _wire_dependencies(self):
        """Wire all module system components with mock external services."""
        # Set environment for module_builder and module_validator
        os.environ["MODULES_DIR"] = str(self.modules_dir)
        os.environ["AUDIT_DIR"] = str(self.audit_dir)

        # Create mock LLM gateway
        mock_provider = MockLLMProvider()
        pref = ModelPreference(provider_name="mock-dev", model_name="mock-dev", priority=0)
        policy = RoutingPolicy(codegen=[pref], repair=[pref], critic=[pref])
        budget = BudgetConfig(max_tokens_per_request=8000)
        self.gateway = LLMGateway(
            providers={"mock-dev": mock_provider},
            routing_policy=policy,
            budget_config=budget,
        )

        # Wire gateway into module_builder
        from tools.builtin import module_builder
        importlib.reload(module_builder)
        module_builder.set_llm_gateway(self.gateway)

        # Wire module_installer with mock deps
        from tools.builtin import module_installer
        importlib.reload(module_installer)

        mock_loader = MagicMock()
        handle = MagicMock()
        handle.is_loaded = True
        handle.error = None
        mock_loader.load_module.return_value = handle

        mock_registry = MagicMock()
        module_installer.set_installer_deps(
            loader=mock_loader,
            registry=mock_registry,
            credential_store=MagicMock(),
        )

        # Create dev-mode managers
        self.audit_log = DevModeAuditLog(self.audit_dir)
        self.draft_manager = DraftManager(
            drafts_dir=self.drafts_dir,
            modules_dir=self.modules_dir,
            audit_log=self.audit_log,
        )
        self.version_manager = VersionManager(
            db_path=self.db_path,
            audit_log=self.audit_log,
        )

    def cmd_build(self, module_id: str):
        """Full pipeline: scaffold → validate → install."""
        from tools.builtin.module_builder import build_module

        parts = module_id.split("/")
        if len(parts) != 2:
            print(f"Error: module_id must be 'category/platform', got '{module_id}'")
            return

        category, platform = parts

        print(f"\n{'='*60}")
        print(f"  BUILD: {module_id}")
        print(f"{'='*60}\n")

        # Step 1: Scaffold
        print("[1/3] Scaffolding module...")
        result = build_module(
            name=platform,
            category=category,
            platform=platform,
            description=f"Dev sandbox module: {module_id}",
            auth_type="api_key",
        )
        print(f"  Status: {result.get('status')}")
        if result.get("status") != "success":
            print(f"  Error: {result.get('error', 'unknown')}")
            return

        # Step 2: Validate (static only — no sandbox)
        print("[2/3] Validating module (static checks)...")
        from tools.builtin.module_validator import validate_module
        val_result = validate_module(module_id)
        print(f"  Status: {val_result.get('status')}")

        if val_result.get("fix_hints"):
            print("  Fix hints:")
            for hint in val_result["fix_hints"]:
                print(f"    - [{hint.get('category')}] {hint.get('message')}")

        # Step 3: Install
        print("[3/3] Installing module...")
        from tools.builtin.module_installer import install_module

        # Build attestation from validation
        manifest = ModuleManifest.load(self.modules_dir, module_id)
        bundle = ArtifactBundleBuilder.build_from_directory(
            directory=self.modules_dir / category / platform,
            job_id="dev_build",
            attempt_id=1,
            module_id=module_id,
        )
        attestation = {
            "bundle_sha256": bundle.bundle_sha256,
            "validation_report": val_result,
        }

        # Update manifest status to VALIDATED for install guard
        if manifest:
            manifest.status = ModuleStatus.VALIDATED.value
            manifest.save(self.modules_dir)

        install_result = install_module(module_id, attestation)
        print(f"  Status: {install_result.get('status')}")

        print(f"\n  Module installed at: {self.modules_dir / category / platform}")
        print(f"  Bundle SHA256: {bundle.bundle_sha256[:16]}...")

    def cmd_validate(self, module_id: str):
        """Run static validation only."""
        from tools.builtin.module_validator import validate_module

        print(f"\nValidating {module_id}...")
        result = validate_module(module_id)
        print(f"Status: {result.get('status')}")
        print(json.dumps(result, indent=2, default=str))

    def cmd_draft_create(self, module_id: str):
        """Create a draft from an installed module."""
        result = self.draft_manager.create_draft(module_id, actor="dev")
        print(f"Status: {result.get('status')}")
        if result.get("status") == "success":
            print(f"Draft ID: {result.get('draft_id')}")
            print(f"Workspace: {self.drafts_dir / result.get('draft_id', '')}")
        else:
            print(f"Error: {result.get('error')}")

    def cmd_draft_edit(self, draft_id: str, filepath: str):
        """Edit a draft file using $EDITOR."""
        draft_workspace = self.drafts_dir / draft_id / "files"
        target = draft_workspace / filepath
        if not target.exists():
            print(f"Error: file not found: {target}")
            return

        editor = os.environ.get("EDITOR", "vi")
        original = target.read_text()

        try:
            subprocess.run([editor, str(target)], check=True)
            new_content = target.read_text()
            if new_content != original:
                result = self.draft_manager.edit_file(
                    draft_id, filepath, new_content, actor="dev"
                )
                print(f"Status: {result.get('status')}")
            else:
                print("No changes detected.")
        except subprocess.CalledProcessError:
            print("Editor exited with error.")

    def cmd_draft_validate(self, draft_id: str):
        """Validate a draft (static checks with mock validator)."""
        def mock_validator(module_path):
            return {"status": "success", "report": {"self_check": "passed", "static_results": []}}

        result = self.draft_manager.validate_draft(
            draft_id, actor="dev", validator_func=mock_validator,
        )
        print(f"Status: {result.get('status')}")
        if result.get("bundle_sha256"):
            print(f"Bundle SHA256: {result['bundle_sha256'][:16]}...")

    def cmd_draft_promote(self, draft_id: str):
        """Promote a validated draft."""
        def mock_installer(module_id, attestation):
            return {"status": "success"}

        result = self.draft_manager.promote_draft(
            draft_id, actor="dev", installer_func=mock_installer,
        )
        print(f"Status: {result.get('status')}")
        if result.get("status") == "success":
            print(f"Module: {result.get('module_id')}")
            print(f"Bundle: {result.get('bundle_sha256', '')[:16]}...")

    def cmd_draft_list(self):
        """List all drafts."""
        drafts = self.draft_manager.list_drafts()
        if not drafts:
            print("No drafts found.")
            return
        for d in drafts:
            print(f"  {d.get('draft_id', 'unknown')}: "
                  f"state={d.get('state', '?')}, "
                  f"module={d.get('module_id', '?')}")

    def cmd_rollback(self, module_id: str, target_version: str):
        """Rollback to a prior version."""
        result = self.version_manager.rollback_to_version(
            module_id=module_id,
            target_version_id=target_version,
            actor="dev",
            reason="Dev sandbox rollback",
        )
        if result:
            print(f"Rolled back to: {target_version}")
        else:
            print(f"Error: rollback failed for {module_id} → {target_version}")

    def cmd_status(self, module_id: Optional[str] = None):
        """Show module/draft status."""
        print(f"\nWorkspace: {self.workspace}\n")

        # List modules
        print("Modules:")
        if self.modules_dir.exists():
            for cat in sorted(self.modules_dir.iterdir()):
                if cat.is_dir() and not cat.name.startswith("."):
                    for plat in sorted(cat.iterdir()):
                        if plat.is_dir():
                            mid = f"{cat.name}/{plat.name}"
                            manifest_file = plat / "manifest.json"
                            status = "unknown"
                            if manifest_file.exists():
                                try:
                                    m = json.loads(manifest_file.read_text())
                                    status = m.get("status", "unknown")
                                except Exception:
                                    pass
                            print(f"  {mid}: {status}")

        # List drafts
        print("\nDrafts:")
        drafts = self.draft_manager.list_drafts()
        if not drafts:
            print("  (none)")
        else:
            for d in drafts:
                print(f"  {d.get('draft_id', 'unknown')}: "
                      f"state={d.get('state', '?')}, "
                      f"module={d.get('module_id', '?')}")

        # Show versions
        if module_id:
            versions = self.version_manager.list_versions(module_id)
            active = self.version_manager.get_active_version(module_id)
            print(f"\nVersions for {module_id}:")
            for v in versions:
                marker = " (active)" if active and v.version_id == active.version_id else ""
                print(f"  {v.version_id}: sha={v.bundle_sha256[:12]}...{marker}")


def main():
    parser = argparse.ArgumentParser(
        prog="nexus-dev",
        description="NEXUS Dev Sandbox — local development tool for the self-evolution pipeline",
    )
    parser.add_argument(
        "--workspace", type=Path, default=None,
        help="Workspace directory (default: ~/.nexus-dev)",
    )

    subparsers = parser.add_subparsers(dest="command")

    # build
    build_p = subparsers.add_parser("build", help="Build module (full pipeline)")
    build_p.add_argument("module_id", help="Module ID (category/platform)")

    # validate
    val_p = subparsers.add_parser("validate", help="Validate module (static checks)")
    val_p.add_argument("module_id", help="Module ID (category/platform)")

    # draft
    draft_p = subparsers.add_parser("draft", help="Draft lifecycle commands")
    draft_sub = draft_p.add_subparsers(dest="draft_action")

    create_p = draft_sub.add_parser("create", help="Create draft from module")
    create_p.add_argument("module_id")

    edit_p = draft_sub.add_parser("edit", help="Edit draft file")
    edit_p.add_argument("draft_id")
    edit_p.add_argument("file_path")

    validate_p = draft_sub.add_parser("validate", help="Validate draft")
    validate_p.add_argument("draft_id")

    promote_p = draft_sub.add_parser("promote", help="Promote validated draft")
    promote_p.add_argument("draft_id")

    draft_sub.add_parser("list", help="List all drafts")

    # rollback
    rb_p = subparsers.add_parser("rollback", help="Rollback to prior version")
    rb_p.add_argument("module_id")
    rb_p.add_argument("target_version")

    # status
    status_p = subparsers.add_parser("status", help="Show module status")
    status_p.add_argument("module_id", nargs="?")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    sandbox = DevSandbox(workspace=args.workspace)

    if args.command == "build":
        sandbox.cmd_build(args.module_id)
    elif args.command == "validate":
        sandbox.cmd_validate(args.module_id)
    elif args.command == "draft":
        if args.draft_action == "create":
            sandbox.cmd_draft_create(args.module_id)
        elif args.draft_action == "edit":
            sandbox.cmd_draft_edit(args.draft_id, args.file_path)
        elif args.draft_action == "validate":
            sandbox.cmd_draft_validate(args.draft_id)
        elif args.draft_action == "promote":
            sandbox.cmd_draft_promote(args.draft_id)
        elif args.draft_action == "list":
            sandbox.cmd_draft_list()
        else:
            draft_p.print_help()
    elif args.command == "rollback":
        sandbox.cmd_rollback(args.module_id, args.target_version)
    elif args.command == "status":
        sandbox.cmd_status(args.module_id)


if __name__ == "__main__":
    main()
