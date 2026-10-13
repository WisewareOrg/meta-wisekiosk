"""Target-suite setup: get the board onto `bench_candidate` before any test runs."""

import subprocess

import pytest
from tenacity import Retrying, stop_after_delay, wait_fixed

_WAIT_TIMEOUT = 300
_WAIT_INTERVAL = 5


@pytest.fixture(scope="session", autouse=True)
def install_candidate(target, bench_candidate):
    """Install `bench_candidate` on the board through the layer's own OTA recipes.

    No-op when `bench_candidate` is None -- no candidate was built this run. Otherwise
    runs `just kiosk-ota` and `just kiosk-reboot` against the board the target's
    NetworkService names, then reconnects labgrid's own SSH session: the reboot leaves
    labgrid's control master stale even once the board itself is back up.
    """
    if bench_candidate is None:
        return
    driver = target.get_driver("SSHDriver")
    host = f"{driver.networkservice.username}@{driver.networkservice.address}"
    subprocess.run(["just", "kiosk-ota", host], check=True)
    subprocess.run(["just", "kiosk-reboot", host], check=True)
    for attempt in Retrying(
        stop=stop_after_delay(_WAIT_TIMEOUT),
        wait=wait_fixed(_WAIT_INTERVAL),
        reraise=True,
    ):
        with attempt:
            target.deactivate(driver)
            target.activate(driver)
            driver.run("true")
