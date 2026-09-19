"""
The orchestrator's tool registration must build without the gRPC service.

Regression: a boot-time AttributeError in the registration block (a package
attribute shadowing a submodule) was only discoverable by starting the
container. This test runs the same code path with real tool instances.
"""
import pytest

from orchestrator.tool_registration import ALIAS_NAMES, PRIMARY_NAMES, register_agent_tools
from tools.registry import LocalToolRegistry


@pytest.fixture()
def registry():
    from tools.builtin.code_executor import CodeExecutorTool
    from tools.builtin.knowledge_search import KnowledgeSearchTool
    from tools.builtin.knowledge_store import KnowledgeStoreTool
    from tools.builtin.math_solver import MathSolverTool
    from tools.builtin.module_admin import ModuleAdminTool
    from tools.builtin.module_pipeline import ModulePipelineTool
    from tools.builtin.user_context import UserContextTool
    from tools.builtin.web_tools import WebTool

    reg = LocalToolRegistry()
    register_agent_tools(
        reg,
        user_context_tool=UserContextTool(),
        web_tool=WebTool(),
        knowledge_search_tool=KnowledgeSearchTool(),
        knowledge_store_tool=KnowledgeStoreTool(),
        math_tool=MathSolverTool(),
        code_executor_tool=CodeExecutorTool(),
        module_pipeline_tool=ModulePipelineTool(),
        module_admin_tool=ModuleAdminTool(),
    )
    return reg


def test_every_expected_name_is_registered(registry):
    assert set(PRIMARY_NAMES) | set(ALIAS_NAMES) <= set(registry.tools)


def test_no_tool_is_exported_as_opaque_kwargs(registry):
    opaque = [
        name for name, schema in registry.schemas.items()
        if "kwargs" in schema["parameters"]["properties"]
    ]
    assert opaque == []


def test_build_chain_aliases_carry_the_legacy_signatures(registry):
    params = registry.schemas["build_module"]["parameters"]
    assert params["required"] == ["name", "category"]
    assert registry.schemas["write_module_code"]["parameters"]["required"] == ["module_id", "adapter_code"]
    assert registry.schemas["validate_module"]["parameters"]["required"] == ["module_id"]
    assert registry.schemas["install_module"]["parameters"]["required"] == ["module_id"]


def test_composite_primaries_require_action(registry):
    for name in ("module_pipeline", "module_admin"):
        params = registry.schemas[name]["parameters"]
        assert params["required"] == ["action"]
        assert params["properties"]["action"]["enum"]


def test_alias_injects_action_and_reaches_the_composite_tool(registry):
    # validate_module -> module_pipeline(action="validate", module_id=...). The
    # module does not exist, so the pipeline reports an error — but through the
    # right action, not "Missing required 'action' parameter".
    result = registry.tools["validate_module"](module_id="nope/missing")
    assert "Missing required 'action'" not in str(result)
