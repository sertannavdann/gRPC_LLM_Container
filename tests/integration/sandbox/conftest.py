"""
pytest configuration for sandbox integration tests.

These tests are standalone and don't require Docker services.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def skip_docker_check():
    """
    Override parent conftest to skip Docker service checks.

    Sandbox tests are standalone unit/integration tests that test
    the policy and runner modules directly without requiring
    the full Docker stack.
    """
    yield
