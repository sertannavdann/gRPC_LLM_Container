"""
pytest configuration for install integration tests.

These tests are standalone and don't require Docker services.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """Override parent test_environment fixture."""
    yield


@pytest.fixture(scope="session", autouse=True)
def llm_warmup(test_environment):
    """Override parent llm_warmup fixture."""
    yield
