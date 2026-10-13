"""Target-suite setup: get the board onto `bench_candidate` before any test runs."""

import subprocess

import pytest


@pytest.fixture(scope="session", autouse=True)
def install_candidate(target, bench_candidate):
    """Install `bench_candidate` on the board through the layer's own OTA recipes.

    No-op when `bench_candidate` is None -- no candidate was built this run. Otherwise
    runs `just kiosk-ota` and `just kiosk-reboot` against the board the target's
    NetworkService names -- read without activating labgrid's own SSH driver, since
    `kiosk-ota`'s own build and transfer need no ssh connection of ours -- then gets the
    SSHDriver for the first time, fresh, after the reboot `kiosk-reboot` already waited
    through: activating raises if labgrid's master cannot connect.
    """
    if bench_candidate is None:
        return
    service = target.get_resource("NetworkService")
    host = f"{service.username}@{service.address}"
    subprocess.run(["just", "kiosk-ota", host], check=True)
    subprocess.run(["just", "kiosk-reboot", host], check=True)
    target.get_driver("SSHDriver")
