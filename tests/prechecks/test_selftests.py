"""Runs every `*-test.*` script in this directory and asserts it exits 0."""

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SELFTESTS = sorted(HERE.glob("*-test.*"))


@pytest.mark.parametrize("script", SELFTESTS, ids=lambda path: path.name)
def test_selftest_passes(script: Path) -> None:
    """The self-test exits 0; its output is the failure message.

    Args:
        script: the self-test, run from the repository root.
    """
    argv = [sys.executable if script.suffix == ".py" else "bash", str(script)]
    run = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
    assert run.returncode == 0, f"{script.name} exited {run.returncode}\n{run.stdout}{run.stderr}"


def test_selftests_exist() -> None:
    """The glob finds the self-tests, so an empty parametrization cannot pass."""
    assert SELFTESTS
