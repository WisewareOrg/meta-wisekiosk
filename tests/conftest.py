"""Shared setup: get the board onto `bench_candidate`, then print its commit."""

import subprocess
import time

import pytest

COMMAND_TIMEOUT_SECONDS = 10


@pytest.fixture(scope="session")
def run_checked(target):
    """Build a `run_checked` that runs a command on the board and asserts it returned 0.

    Args:
        target (labgrid.Target): names the board's SSHDriver.

    Returns:
        Callable[[str, float | None], list[str]]: `run_checked(cmd, timeout)`, which returns
            `cmd`'s combined stdout and stderr lines and raises AssertionError if `cmd`
            returned nonzero. `timeout` defaults to `COMMAND_TIMEOUT_SECONDS`; None means none.
    """
    driver = target.get_driver("SSHDriver")

    def run_checked(cmd, timeout=COMMAND_TIMEOUT_SECONDS):
        """Run `cmd` on the board and assert it returned 0.

        Args:
            cmd (str): the command to run.
            timeout (float | None): forwarded to `driver.run`.

        Returns:
            list[str]: `cmd`'s combined stdout and stderr lines.

        Raises:
            AssertionError: `cmd` returned nonzero.
        """
        stdout, stderr, returncode = driver.run(cmd, timeout=timeout)
        output = stdout + stderr
        assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
        return output

    return run_checked


@pytest.fixture(scope="session")
def board_clock(target):
    """Build a `board_clock` that reads the board's uptime and how far its clock is off the host's.

    Args:
        target (labgrid.Target): names the board's SSHDriver.

    Returns:
        Callable[[], tuple[float, float] | None]: `board_clock()`, which returns the board's
            uptime in seconds and board `date +%s` minus host `time.time()`, or None if the
            read failed or timed out.
    """
    driver = target.get_driver("SSHDriver")

    def board_clock():
        """The board's uptime and its clock minus the host's, from one command.

        Returns:
            tuple[float, float] | None: the board's uptime in seconds and board `date +%s`
                minus host `time.time()`, or None if the read failed or timed out.
        """
        try:
            stdout, _stderr, returncode = driver.run(
                "cat /proc/uptime; date +%s", timeout=COMMAND_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            return None
        if returncode != 0:
            return None
        return float(stdout[0].split()[0]), int(stdout[1].strip()) - time.time()

    return board_clock


@pytest.fixture(scope="session")
def restart_board(target):
    """Build a `restart_board` that restarts the board and reconnects the SSHDriver.

    Args:
        target (labgrid.Target): names the board's NetworkService and SSHDriver.

    Returns:
        Callable[[], None]: `restart_board()`, which runs `just kiosk-reboot` against the
            board the NetworkService names, then deactivates and activates the SSHDriver.
            Raises subprocess.CalledProcessError if `just kiosk-reboot` exits nonzero, and
            whatever the SSHDriver's own activation raises if the board is not reached.
    """
    driver = target.get_driver("SSHDriver")
    service = target.get_resource("NetworkService")
    host = f"{service.username}@{service.address}"

    def restart_board():
        """Restart the board and reconnect the SSHDriver."""
        restart_board()
        target.deactivate(driver)
        target.activate(driver)

    return restart_board


@pytest.fixture(scope="session")
def install_candidate(target, bench_candidate, restart_board):
    """Install `bench_candidate` on the board, if there is one, then print its commit.

    Installs by running `just kiosk-ota` against the board the target's NetworkService
    names, then `restart_board`. Either way, gets the SSHDriver, reads
    /etc/buildinfo, and prints the board's meta-wisekiosk commit as
    `board_commit=<sha>`.

    Args:
        target (labgrid.Target): names the board's NetworkService and SSHDriver.
        bench_candidate (str | None): the commit under test, or None outside a build.
        restart_board (Callable[[], None]): the `restart_board` fixture.

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
        restart_board()
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
