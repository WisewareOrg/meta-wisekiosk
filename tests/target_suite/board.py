"""The board: running a command on it and asserting it returned 0."""

from page import POLL_ATTEMPT_TIMEOUT_SECONDS


def run_checked(driver, cmd):
    """Run `cmd` on the board and assert it returned 0.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.
        cmd (str): the command to run.

    Returns:
        list[str]: `cmd`'s combined stdout and stderr lines.

    Raises:
        AssertionError: `cmd` returned nonzero.
    """
    stdout, stderr, returncode = driver.run(cmd, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
    output = stdout + stderr
    assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
    return output
