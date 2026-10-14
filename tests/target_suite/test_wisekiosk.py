"""Target suite: the WiseKiosk instance's page, and its recovery from a backend crash."""

import subprocess
import time

# busybox wget: rc 0 only on 2xx
PAGE_URL = "http://127.0.0.1:8080/"
BOUND_SECONDS = 60
POLL_INTERVAL_SECONDS = 2
POLL_ATTEMPT_TIMEOUT_SECONDS = 10


def _poll_for_page(driver):
    """Poll `PAGE_URL` on the board until it serves an HTML page or the bound elapses.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.

    Returns:
        bool: whether the page served an HTML document within `BOUND_SECONDS`.
    """
    deadline = time.monotonic() + BOUND_SECONDS
    while True:
        try:
            stdout, stderr, returncode = driver.run(
                f"wget -q -O- {PAGE_URL}", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS
            )
            output = "\n".join(stdout + stderr).strip()
            if returncode == 0 and "<html" in output:
                return True
        except subprocess.TimeoutExpired:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_INTERVAL_SECONDS)


def test_page_serves(target, record_property):
    """The WiseKiosk instance's page is served on the appliance."""
    driver = target.get_driver("SSHDriver")
    stdout, stderr, returncode = driver.run(f"wget -q -O- {PAGE_URL}", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
    output = "\n".join(stdout + stderr).strip()
    assert returncode == 0, f"GET / failed (rc {returncode}): {output}"
    assert "<html" in output, f"GET / did not return an <html> body: {output}"
    record_property("requirement", "TST022")


def test_backend_crash(target, record_property):
    """The instance's page is served again within 60 s of the backend being killed."""
    driver = target.get_driver("SSHDriver")
    assert _poll_for_page(driver), "page did not serve before the crash was induced"

    stdout, stderr, returncode = driver.run(
        "systemctl show -p MainPID --value wisekiosk.service", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS
    )
    output = "\n".join(stdout + stderr).strip()
    assert returncode == 0, f"could not read MainPID before the crash: {output}"
    old_pid = output

    stdout, stderr, returncode = driver.run(
        "systemctl kill --signal=KILL wisekiosk.service", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS
    )
    output = "\n".join(stdout + stderr).strip()
    assert returncode == 0, f"systemctl kill failed (rc {returncode}): {output}"

    assert _poll_for_page(driver), f"page did not serve again within {BOUND_SECONDS}s of the crash"

    stdout, stderr, returncode = driver.run(
        "systemctl show -p MainPID --value wisekiosk.service", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS
    )
    output = "\n".join(stdout + stderr).strip()
    assert returncode == 0, f"could not read MainPID after the crash: {output}"
    new_pid = output
    assert new_pid != "0" and new_pid != old_pid, (
        f"MainPID did not change after the kill (old {old_pid}, new {new_pid})"
    )
    record_property("requirement", "TST032")
