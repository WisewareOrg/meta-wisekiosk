"""The WiseKiosk instance's page: the URL it serves, and polling for it."""

import subprocess
import time

# busybox wget: rc 0 only on 2xx
PAGE_URL = "http://127.0.0.1:8080/"
BOUND_SECONDS = 60
POLL_INTERVAL_SECONDS = 2
POLL_ATTEMPT_TIMEOUT_SECONDS = 10


def poll_for_page(driver):
    """Poll `PAGE_URL` on the board until it serves an HTML page or the bound elapses.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.

    Returns:
        bool: whether the page served an HTML document within `BOUND_SECONDS`.
    """
    deadline = time.monotonic() + BOUND_SECONDS
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            stdout, stderr, returncode = driver.run(
                f"wget -q -O- {PAGE_URL}", timeout=min(POLL_ATTEMPT_TIMEOUT_SECONDS, remaining)
            )
            output = "\n".join(stdout + stderr).strip()
            if returncode == 0 and "<html" in output and time.monotonic() <= deadline:
                return True
        except subprocess.TimeoutExpired:
            pass
        time.sleep(POLL_INTERVAL_SECONDS)
    return False
