"""Diagnostics setup: switch on the shared board setup for every test here."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(install_candidate: tuple[str, bool] | None) -> None:
    """Activate `install_candidate` (tests/conftest.py) for every test in this suite.

    Args:
        install_candidate: the marker and whether the journal held it before the install; None
            outside a build.
    """
