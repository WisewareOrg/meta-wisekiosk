"""Diagnostics setup: switch on the shared board setup for every test here."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(install_candidate):
    """Activate `install_candidate` (tests/conftest.py) for every test in this suite."""
