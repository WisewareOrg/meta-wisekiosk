"""Shared setup: get the board onto `bench_candidate`, then print its commit."""

import subprocess
import time

import pytest

COMMAND_TIMEOUT_SECONDS = 10


class Board:
    """The board under test: its remote shell, its clock, and its restart.

    Attributes:
        host (str): `user@address` of the board, as the `just kiosk-*` recipes take it.
        PAGE_URL (str): the WiseKiosk instance's page, as the board fetches it. busybox wget
            returns 0 only on 2xx.
        PAGE_BOUND_SECONDS (float): how long `wait_for_page` waits for the page.
        PAGE_POLL_INTERVAL_SECONDS (float): the pause between `wait_for_page`'s attempts.
        PAGE_ATTEMPT_TIMEOUT_SECONDS (float): the longest one page fetch may take.
    """

    PAGE_URL = "http://127.0.0.1:8080/"
    PAGE_BOUND_SECONDS = 60
    PAGE_POLL_INTERVAL_SECONDS = 2
    PAGE_ATTEMPT_TIMEOUT_SECONDS = 10

    def __init__(self, target):
        """Bind to the target's SSHDriver and NetworkService.

        Args:
            target (labgrid.Target): names the board's SSHDriver and NetworkService.
        """
        self._target = target
        self._driver = target.get_driver("SSHDriver")
        service = target.get_resource("NetworkService")
        self.host = f"{service.username}@{service.address}"

    def run(self, cmd, check=False, timeout=COMMAND_TIMEOUT_SECONDS):
        """Run `cmd` on the board.

        Args:
            cmd (str): the command to run.
            check (bool): assert the command returned 0.
            timeout (float | None): forwarded to `driver.run`; None means no timeout.

        Returns:
            tuple[list[str], list[str], int]: stdout lines, stderr lines and the return code.

        Raises:
            AssertionError: `check` is set and `cmd` returned nonzero.
        """
        stdout, stderr, returncode = self._driver.run(cmd, timeout=timeout)
        if check:
            output = stdout + stderr
            assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
        return stdout, stderr, returncode

    def put(self, src, dst):
        """Copy the host file `src` to `dst` on the board.

        Args:
            src (str): path on the host.
            dst (str): path on the board.
        """
        self._driver.put(src, dst)

    def get(self, src, dst):
        """Copy `src` on the board to the host path `dst`.

        Args:
            src (str): path on the board.
            dst (str): path on the host.
        """
        self._driver.get(src, dst)

    def forward_remote_port(self, local, remote):
        """Forward the board's port `remote` to the host's port `local`.

        Args:
            local (int): port on the host.
            remote (int): port on the board.

        Returns:
            contextlib.AbstractContextManager: labgrid's forwarding context manager.
        """
        return self._driver.forward_remote_port(local, remote)

    def connect(self):
        """Activate the board's SSHDriver."""
        self._target.activate(self._driver)

    def disconnect(self):
        """Deactivate the board's SSHDriver."""
        self._target.deactivate(self._driver)

    def clock(self):
        """The board's uptime and its clock minus the host's, from one command.

        Returns:
            tuple[float, float] | None: the board's uptime in seconds and board `date +%s`
                minus host `time.time()`, or None if the read failed or timed out.
        """
        try:
            stdout, _stderr, returncode = self._driver.run(
                "cat /proc/uptime; date +%s", timeout=COMMAND_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            return None
        if returncode != 0:
            return None
        return float(stdout[0].split()[0]), int(stdout[1].strip()) - time.time()

    def commit(self):
        """The meta-wisekiosk commit the board's image was built from.

        Returns:
            str: the commit named by the meta-wisekiosk line of /etc/buildinfo.

        Raises:
            AssertionError: /etc/buildinfo cannot be read, or carries no meta-wisekiosk
                line.
        """
        stdout, _stderr, returncode = self.run("cat /etc/buildinfo", timeout=None)
        assert returncode == 0, "could not read /etc/buildinfo on the board"
        line = next(
            (entry for entry in stdout if entry.split()[:2] == ["meta-wisekiosk", "="]),
            None,
        )
        assert line is not None, f"no meta-wisekiosk layer line in buildinfo:\n{chr(10).join(stdout)}"
        return line.split()[2].rsplit(":", 1)[-1]

    def fetch_page(self, timeout=PAGE_ATTEMPT_TIMEOUT_SECONDS):
        """Fetch `PAGE_URL` on the board.

        Args:
            timeout (float): forwarded to `run`.

        Returns:
            tuple[int, str]: the return code and the combined stdout and stderr, joined by
                newlines and stripped.

        Raises:
            subprocess.TimeoutExpired: the fetch ran past `timeout`.
        """
        stdout, stderr, returncode = self.run(f"wget -q -O- {self.PAGE_URL}", timeout=timeout)
        return returncode, "\n".join(stdout + stderr).strip()

    def wait_for_page(self):
        """Poll `PAGE_URL` until it serves an HTML page or `PAGE_BOUND_SECONDS` elapse.

        Returns:
            bool: whether the page served an HTML document within `PAGE_BOUND_SECONDS`.
        """
        deadline = time.monotonic() + self.PAGE_BOUND_SECONDS
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                returncode, output = self.fetch_page(
                    timeout=min(self.PAGE_ATTEMPT_TIMEOUT_SECONDS, remaining)
                )
                if returncode == 0 and "<html" in output and time.monotonic() <= deadline:
                    return True
            except subprocess.TimeoutExpired:
                pass
            time.sleep(self.PAGE_POLL_INTERVAL_SECONDS)
        return False

    def install_image(self):
        """Install the built image on the board with `just kiosk-ota`.

        Raises:
            subprocess.CalledProcessError: `just kiosk-ota` exits nonzero.
        """
        subprocess.run(["just", "kiosk-ota", self.host], check=True)

    def restart(self):
        """Restart the board and reconnect the SSHDriver.

        Runs `just kiosk-reboot` against the board, then disconnects and connects the
        SSHDriver.

        Raises:
            subprocess.CalledProcessError: `just kiosk-reboot` exits nonzero.
            Exception: the SSHDriver's own activation times out reaching the board.
        """
        subprocess.run(["just", "kiosk-reboot", self.host], check=True)
        self.disconnect()
        self.connect()


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
def install_candidate(bench_candidate, board):
    """Install `bench_candidate` on the board, if there is one, then print its commit.

    Installs by `board.install_image`, then `board.restart`. Either way, prints the board's
    meta-wisekiosk commit as `board_commit=<sha>`.

    Args:
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
        board.install_image()
        board.restart()
    print(f"board_commit={board.commit()}")
