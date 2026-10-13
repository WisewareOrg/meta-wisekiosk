"""The one `driver.run`-wrapper every target-suite module that needs plain text shares."""


def run_text(driver, cmd):
    """`driver.run(cmd)`'s stdout, newline-joined.

    Args:
        driver: A labgrid SSHDriver.
        cmd (str): The command to run.

    Returns:
        str: `cmd`'s stdout, its lines rejoined with newlines.

    Raises:
        RuntimeError: `cmd` exited non-zero.
    """
    stdout, stderr, rc = driver.run(cmd)
    if rc != 0:
        raise RuntimeError(f"{cmd!r} exited {rc}: {stderr}")
    return "\n".join(stdout)
