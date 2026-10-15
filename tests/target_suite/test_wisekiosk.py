"""Target suite: the WiseKiosk instance's page, and its recovery from a backend crash."""

from page import BOUND_SECONDS, PAGE_URL, POLL_ATTEMPT_TIMEOUT_SECONDS, poll_for_page


def test_page_serves(target, record_property):
    """The WiseKiosk instance's page is served on the appliance."""
    driver = target.get_driver("SSHDriver")
    stdout, stderr, returncode = driver.run(f"wget -q -O- {PAGE_URL}", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
    output = "\n".join(stdout + stderr).strip()
    assert returncode == 0, f"GET / failed (rc {returncode}): {output}"
    assert "<html" in output, f"GET / did not return an <html> body: {output}"
    record_property("requirement", "TST022")


def test_backend_crash(target, record_property):
    """The instance's page is served again within `BOUND_SECONDS` of the backend being killed."""
    driver = target.get_driver("SSHDriver")
    assert poll_for_page(driver), "page did not serve before the crash was induced"

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

    assert poll_for_page(driver), f"page did not serve again within {BOUND_SECONDS}s of the crash"

    stdout, stderr, returncode = driver.run(
        "systemctl show -p MainPID --value wisekiosk.service", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS
    )
    output = "\n".join(stdout + stderr).strip()
    assert returncode == 0, f"could not read MainPID after the crash: {output}"
    new_pid = output
    assert new_pid and new_pid != "0" and new_pid != old_pid, (
        f"MainPID did not change after the kill (old {old_pid}, new {new_pid})"
    )
    record_property("requirement", "TST032")
