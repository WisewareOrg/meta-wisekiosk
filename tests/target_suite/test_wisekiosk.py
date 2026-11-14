"""Target suite: the WiseKiosk instance's page, and its recovery from a backend crash."""


def test_page_serves(board, record_property):
    """The WiseKiosk instance's page is served on the appliance."""
    returncode, output = board.fetch_page()
    assert returncode == 0, f"GET / failed (rc {returncode}): {output}"
    assert "<html" in output, f"GET / did not return an <html> body: {output}"
    record_property("requirement", "TST022")


def test_backend_crash(board, record_property):
    """The instance's page is served again within `board.PAGE_BOUND_SECONDS` of the backend being killed."""
    assert board.wait_for_page(), "page did not serve before the crash was induced"

    stdout, stderr, returncode = board.run("systemctl show -p MainPID --value wisekiosk.service")
    output = "\n".join(stdout + stderr).strip()
    assert returncode == 0, f"could not read MainPID before the crash: {output}"
    old_pid = output

    stdout, stderr, returncode = board.run("systemctl kill --signal=KILL wisekiosk.service")
    output = "\n".join(stdout + stderr).strip()
    assert returncode == 0, f"systemctl kill failed (rc {returncode}): {output}"

    assert board.wait_for_page(), f"page did not serve again within {board.PAGE_BOUND_SECONDS}s of the crash"

    stdout, stderr, returncode = board.run("systemctl show -p MainPID --value wisekiosk.service")
    output = "\n".join(stdout + stderr).strip()
    assert returncode == 0, f"could not read MainPID after the crash: {output}"
    new_pid = output
    assert new_pid and new_pid != "0" and new_pid != old_pid, (
        f"MainPID did not change after the kill (old {old_pid}, new {new_pid})"
    )
    record_property("requirement", "TST032")
