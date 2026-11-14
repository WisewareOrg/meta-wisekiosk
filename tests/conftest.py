"""Shared setup: the `Board` the tests drive, and getting it onto `bench_candidate`."""

import subprocess
import time

import pytest
from labgrid.driver.exception import ExecutionError

COMMAND_TIMEOUT_SECONDS = 10


class Board:
    """The board under test: its remote shell, clock, commit, page, image install and restart.

    Attributes:
        host (str): `user@address` of the board, as the `just kiosk-*` recipes take it.
        PAGE_URL (str): the WiseKiosk instance's page, as the board fetches it. busybox wget
            returns 0 only on 2xx.
        PAGE_BOUND_SECONDS (int): how long `wait_for_page` waits for the page.
        PAGE_POLL_INTERVAL_SECONDS (int): the pause between `wait_for_page`'s attempts.
        PAGE_ATTEMPT_TIMEOUT_SECONDS (int): the longest one page fetch may take.
        RESTART_WAIT_SECONDS (int): how long `restart_by` waits for the board to answer in a new
            boot.
        FAULT_SSH_TIMEOUT_SECONDS (int): the backstop on the one-shot ssh that sends `restart_by`'s
            command.
    """

    PAGE_URL = "http://127.0.0.1:8080/"
    PAGE_BOUND_SECONDS = 60
    PAGE_POLL_INTERVAL_SECONDS = 2
    PAGE_ATTEMPT_TIMEOUT_SECONDS = 10
    RESTART_WAIT_SECONDS = 180
    FAULT_SSH_TIMEOUT_SECONDS = 30

    def __init__(self, target):
        """Bind to the target's SSHDriver and NetworkService.

        Getting the SSHDriver activates it, which opens the SSH connection.

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
            subprocess.TimeoutExpired: `cmd` ran past `timeout`.
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
        return self._driver.forward_remote_port(remoteport=remote, localport=local)

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
                minus host `time.time()`, or None if the read returned nonzero or timed out.
        """
        try:
            stdout, _stderr, returncode = self.run("cat /proc/uptime; date +%s")
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

    def page_served(self, timeout=PAGE_ATTEMPT_TIMEOUT_SECONDS):
        """Read `PAGE_URL` once and report whether it served an HTML page.

        Args:
            timeout (float): forwarded to `fetch_page`.

        Returns:
            bool: whether the fetch returned 0 with `<html` in the output; False if it timed out.
        """
        try:
            returncode, output = self.fetch_page(timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
        return returncode == 0 and "<html" in output

    def wait_for_page(self):
        """Poll `PAGE_URL` until it serves an HTML page or `PAGE_BOUND_SECONDS` elapse.

        Returns:
            bool: whether the page served an HTML document within `PAGE_BOUND_SECONDS`.
        """
        deadline = time.monotonic() + self.PAGE_BOUND_SECONDS
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if (
                self.page_served(timeout=min(self.PAGE_ATTEMPT_TIMEOUT_SECONDS, remaining))
                and time.monotonic() <= deadline
            ):
                return True
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

    def reconnect(self):
        """Connect the SSHDriver, retrying every 1 s until the board answers.

        Waits through a reboot in progress. A failed or nonzero read of `true` counts as not back
        yet.

        Raises:
            AssertionError: the board did not answer within `RESTART_WAIT_SECONDS`.
        """
        deadline = time.monotonic() + self.RESTART_WAIT_SECONDS
        while True:
            try:
                self.connect()
            except Exception:  # labgrid's activation timeout is a bare Exception
                connected = False
            else:
                connected = True
                try:
                    if self.run("true")[2] == 0:
                        return
                except (ExecutionError, subprocess.TimeoutExpired):
                    pass
            assert time.monotonic() < deadline, (
                f"the board did not answer within {self.RESTART_WAIT_SECONDS} s"
            )
            if connected:
                self.disconnect()
            time.sleep(1)

    def fresh_ssh_argv(self, *options):
        """The argv of an ssh to the board over its own connection, short of the remote command.

        Carries no control master: the connection is its own TCP session with its own
        authentication, whatever the host's ssh config says.

        Args:
            *options (str): further `-o` options, each as `Name=value`.

        Returns:
            list[str]: `ssh`, the shared and given options, then `host`; the caller appends the
                remote command.
        """
        shared = (
            "BatchMode=yes",
            "StrictHostKeyChecking=no",
            "UserKnownHostsFile=/dev/null",
            "ControlMaster=no",
            "ControlPath=none",
        )
        argv = ["ssh"]
        for option in (*shared, *options):
            argv += ["-o", option]
        return [*argv, self.host]

    def restart_by(self, cmd):
        """Take the board down with `cmd` over a one-shot ssh, then reconnect in a new boot.

        Unlike `restart`, which goes through `just kiosk-reboot`'s 5 s polling, this polls every
        1 s, so a test can time the restart. It disconnects the SSHDriver before sending `cmd`,
        while the board is still up. If the board never answers in a new boot, the SSHDriver is
        left as the last attempt left it, connected if the last connect succeeded.

        Args:
            cmd (str): the command that restarts or crashes the board.

        Raises:
            AssertionError: the opening boot-id read returned nonzero, or the board did not answer
                in a new boot within `RESTART_WAIT_SECONDS`; the message carries how the ssh
                that sent `cmd` ended.
            subprocess.TimeoutExpired: reading the boot id before `cmd` ran past its timeout.
        """
        boot_id_cmd = "cat /proc/sys/kernel/random/boot_id"
        old_boot_id = self.run(boot_id_cmd, check=True)[0][0]
        self.disconnect()
        try:
            sent = subprocess.run(
                [
                    *self.fresh_ssh_argv(
                        "ConnectTimeout=10", "ServerAliveInterval=2", "ServerAliveCountMax=3"
                    ),
                    cmd,
                ],
                capture_output=True,
                text=True,
                timeout=self.FAULT_SSH_TIMEOUT_SECONDS,
            )
            sent_as = f"rc {sent.returncode}, stderr {sent.stderr.strip()[-200:]!r}"
        except subprocess.TimeoutExpired:
            sent_as = f"timed out after {self.FAULT_SSH_TIMEOUT_SECONDS} s"
        deadline = time.monotonic() + self.RESTART_WAIT_SECONDS
        while True:
            try:
                self.connect()
            except Exception:  # labgrid's activation timeout is a bare Exception
                if time.monotonic() >= deadline:
                    break
                time.sleep(1)
                continue
            try:
                stdout, _stderr, returncode = self.run(boot_id_cmd)
                if returncode == 0 and stdout and stdout[0] != old_boot_id:
                    return
            except (ExecutionError, subprocess.TimeoutExpired):
                pass
            if time.monotonic() >= deadline:
                break
            self.disconnect()
            time.sleep(1)
        raise AssertionError(
            f"the board did not answer in a new boot within {self.RESTART_WAIT_SECONDS} s; "
            f"the ssh that sent {cmd!r} ended with {sent_as}"
        )


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
