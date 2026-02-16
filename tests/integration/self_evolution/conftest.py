"""
pytest configuration for self-evolution integration tests.

These tests are standalone and don't require Docker services.
They test the audit module, repair loop logic, and failure fingerprinting.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """
    Override parent test_environment fixture.

    Self-evolution tests don't require Docker services - they're
    standalone unit tests of the audit module logic.
    """
    yield


@pytest.fixture(scope="session", autouse=True)
def llm_warmup(test_environment):
    """Override parent llm_warmup fixture."""
    yield
