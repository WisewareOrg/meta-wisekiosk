"""Shared setup: get the board onto `bench_candidate`, then print its commit."""

import subprocess
import time

import pytest

COMMAND_TIMEOUT_SECONDS = 10


class Board:
    """The board under test: its remote shell, its clock, and its restart.

    Attributes:
        driver (labgrid.driver.SSHDriver): the board's remote shell.
    """

    def __init__(self, target):
        """Bind to the target's SSHDriver and NetworkService.

        Args:
            target (labgrid.Target): names the board's SSHDriver and NetworkService.
        """
        self._target = target
        self.driver = target.get_driver("SSHDriver")
        service = target.get_resource("NetworkService")
        self._host = f"{service.username}@{service.address}"

    def run_checked(self, cmd, timeout=COMMAND_TIMEOUT_SECONDS):
        """Run `cmd` on the board and assert it returned 0.

        Args:
            cmd (str): the command to run.
            timeout (float | None): forwarded to `driver.run`; None means no timeout.

        Returns:
            list[str]: `cmd`'s combined stdout and stderr lines.

        Raises:
            AssertionError: `cmd` returned nonzero.
        """
        stdout, stderr, returncode = self.driver.run(cmd, timeout=timeout)
        output = stdout + stderr
        assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
        return output

    def clock(self):
        """The board's uptime and its clock minus the host's, from one command.

        Returns:
            tuple[float, float] | None: the board's uptime in seconds and board `date +%s`
                minus host `time.time()`, or None if the read failed or timed out.
        """
        try:
            stdout, _stderr, returncode = self.driver.run(
                "cat /proc/uptime; date +%s", timeout=COMMAND_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            return None
        if returncode != 0:
            return None
        return float(stdout[0].split()[0]), int(stdout[1].strip()) - time.time()

    def restart(self):
        """Restart the board and reconnect the SSHDriver.

        Runs `just kiosk-reboot` against the board, then deactivates and activates the
        SSHDriver.

        Raises:
            subprocess.CalledProcessError: `just kiosk-reboot` exits nonzero.
            Exception: the SSHDriver's own activation times out reaching the board.
        """
        subprocess.run(["just", "kiosk-reboot", self._host], check=True)
        self._target.deactivate(self.driver)
        self._target.activate(self.driver)


@pytest.fixture(scope="session")
def board(target):
    """The `Board` for the target.

    Args:
        target (labgrid.Target): names the board's SSHDriver and NetworkService.

    Returns:
        Board: the board under test.
    """
    return Board(target)


@pytest.fixture(scope="session")
def install_candidate(target, bench_candidate, board):
    """Install `bench_candidate` on the board, if there is one, then print its commit.

    Installs by running `just kiosk-ota` against the board the target's NetworkService
    names, then `board.restart`. Either way, gets the SSHDriver, reads
    /etc/buildinfo, and prints the board's meta-wisekiosk commit as
    `board_commit=<sha>`.

    Args:
        target (labgrid.Target): names the board's NetworkService and SSHDriver.
        bench_candidate (str | None): the commit under test, or None outside a build.
        board (Board): the board under test.

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
        board.restart()
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
