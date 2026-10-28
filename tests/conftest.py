"""Shared setup: get the board onto `bench_candidate`, then print its commit."""

import subprocess

import pytest


@pytest.fixture(scope="session")
def install_candidate(target, bench_candidate):
    """Install `bench_candidate` on the board, if there is one, then print its commit.

    Installs by running `just kiosk-ota` and `just kiosk-reboot` against the board the
    target's NetworkService names. Either way, gets the SSHDriver, reads
    /etc/buildinfo, and prints the board's meta-wisekiosk commit as
    `board_commit=<sha>`.

    Args:
        target (labgrid.Target): names the board's NetworkService and SSHDriver.
        bench_candidate (str | None): the commit under test, or None outside a build.

    Raises:
        subprocess.CalledProcessError: `just kiosk-ota` or `just kiosk-reboot` exits
            nonzero.
        Exception: the SSHDriver's own activation times out reaching the board.
        AssertionError: /etc/buildinfo cannot be read, or carries no meta-wisekiosk
            line.
    """
    if bench_candidate is not None:
        service = target.get_resource("NetworkService")
        host = f"{service.username}@{service.address}"
        subprocess.run(["just", "kiosk-ota", host], check=True)
        subprocess.run(["just", "kiosk-reboot", host], check=True)
    driver = target.get_driver("SSHDriver")
    stdout, _stderr, returncode = driver.run("cat /etc/buildinfo")
    assert returncode == 0, "could not read /etc/buildinfo on the board"
    line = next(
        (entry for entry in stdout if entry.split()[:2] == ["meta-wisekiosk", "="]),
        None,
    )
    assert line is not None, f"no meta-wisekiosk layer line in buildinfo:\n{chr(10).join(stdout)}"
    board_commit = line.split()[2].rsplit(":", 1)[-1]
    print(f"board_commit={board_commit}")
