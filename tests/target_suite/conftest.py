"""Target-suite setup: get the board onto `bench_candidate`, then print its commit."""

import subprocess

import pytest


@pytest.fixture(scope="session", autouse=True)
def install_candidate(target, bench_candidate):
    """Install `bench_candidate` on the board, then print the board's commit.

    No installation when `bench_candidate` is None -- no candidate was built this run.
    Otherwise runs `just kiosk-ota` and `just kiosk-reboot` against the board the
    target's NetworkService names -- read without activating labgrid's own SSH driver,
    since `kiosk-ota`'s own build and transfer need no ssh connection of ours. Either
    way, gets the SSHDriver -- fresh, for the first time, after `kiosk-reboot` already
    waited through the reboot when there was one; activating raises if labgrid's master
    cannot connect -- reads /etc/buildinfo, and prints the board's meta-wisekiosk commit
    so pytest captures it into the run's report.
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
