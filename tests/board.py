"""The board under test as the tests drive it: its shell, page, boot state, image install and restarts."""

import json
import subprocess
from contextlib import AbstractContextManager

from labgrid import Target
from labgrid.driver.exception import ExecutionError
from poll import GIVE_UP_SECONDS, poll


class Board:
    """The board under test: its remote shell, page, commit, image install and restarts.

    Wraps the target's SSHDriver and carries every call to it, so no test reaches the driver. Every
    other method is a read or a restart the tests make; a read that needs a clock stamp takes the
    board's uptime from the same command (`timed`).

    Attributes:
        host: `user@address` of the board, as the `just kiosk-*` recipes take it.
        CONFIG_PATH: the live configuration file on the board.
        DEFAULT_CONFIG_PATH: the image's default configuration, which the board reseeds the live file
            from when it holds none.
        BOOT_ID_CMD: prints the kernel's boot id, which differs in each boot.
        BOOT_VARIABLES_CMD: prints BOOT_ORDER and each slot's BOOT_x_LEFT as name=value lines.
    """

    CONFIG_PATH = "/data/config/config.json"
    DEFAULT_CONFIG_PATH = "/usr/share/wisekiosk/config.example.json"
    BOOT_ID_CMD = "cat /proc/sys/kernel/random/boot_id"
    BOOT_VARIABLES_CMD = "fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT"
    _COMMAND_TIMEOUT_SECONDS = 10
    # busybox wget returns 0 only on 2xx
    _PAGE_FETCH_CMD = "wget -q -O- http://127.0.0.1:8080/"
    _PAGE_TIMEOUT_SECONDS = 10
    _PAGE_WAIT_SECONDS = 60
    _PAGE_POLL_SECONDS = 2
    _RESTART_WAIT_SECONDS = 180
    # `just kiosk-reboot`'s wait
    _REBOOT_WAIT_SECONDS = 300
    _FAULT_SSH_TIMEOUT_SECONDS = 30

    def __init__(self, target: Target) -> None:
        """Bind to the target's SSHDriver and NetworkService.

        Getting the SSHDriver activates it, which opens the SSH connection.

        Args:
            target: names the board's SSHDriver and NetworkService.
        """
        self._target = target
        self._driver = target.get_driver("SSHDriver")
        service = target.get_resource("NetworkService")
        self.host = f"{service.username}@{service.address}"

    def run(
        self, cmd: str, check: bool = False, timeout: float | None = _COMMAND_TIMEOUT_SECONDS
    ) -> tuple[list[str], list[str], int]:
        """Run `cmd` on the board.

        Args:
            cmd: the command to run.
            check: assert the command returned 0.
            timeout: forwarded to `driver.run`; None means no timeout.

        Returns:
            The stdout lines, the stderr lines and the return code.

        Raises:
            AssertionError: `check` is set and `cmd` returned nonzero.
            subprocess.TimeoutExpired: `cmd` ran past `timeout`.
        """
        stdout, stderr, returncode = self._driver.run(cmd, timeout=timeout)
        if check:
            output = stdout + stderr
            assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
        return stdout, stderr, returncode

    def read(self, cmd: str, timeout: float | None = _COMMAND_TIMEOUT_SECONDS) -> str:
        """Run `cmd` on the board and return its stdout.

        Args:
            cmd: the command to run; it must return 0.
            timeout: forwarded to `run`.

        Returns:
            The stdout lines joined by newlines, stripped.

        Raises:
            AssertionError: `cmd` returned nonzero.
            subprocess.TimeoutExpired: `cmd` ran past `timeout`.
        """
        return "\n".join(self.run(cmd, check=True, timeout=timeout)[0]).strip()

    def timed(
        self, cmd: str = "true", check: bool = False, timeout: float | None = _COMMAND_TIMEOUT_SECONDS
    ) -> tuple[float, list[str], list[str], int]:
        """Run `cmd` on the board, stamped with the board's uptime at its start.

        Args:
            cmd: the command to run.
            check: assert `cmd` returned 0.
            timeout: forwarded to `run`.

        Returns:
            The board's uptime in seconds, the stdout lines after the uptime line, the stderr lines
            and `cmd`'s return code.

        Raises:
            AssertionError: `check` is set and `cmd` returned nonzero.
            ExecutionError: stdout carries no uptime line, so the session failed; a poll takes it as
                a failed read.
            subprocess.TimeoutExpired: the command ran past `timeout`.
        """
        stdout, stderr, returncode = self.run(f"cat /proc/uptime; {cmd}", check=check, timeout=timeout)
        try:
            uptime = float(stdout[0].split()[0])
        except (IndexError, ValueError):
            raise ExecutionError(cmd, stdout, stderr) from None
        return uptime, stdout[1:], stderr, returncode

    def unmount_if_mounted(self, path: str) -> None:
        """Unmount `path` on the board if it is a mount point; a path that is not one is fine.

        Args:
            path: the mount point on the board.

        Raises:
            AssertionError: the path is mounted and `umount` fails.
        """
        self.run(f"if grep -q ' {path} ' /proc/self/mountinfo; then umount {path}; fi", check=True)

    def put(self, src: str, dst: str) -> None:
        """Copy the host file `src` to `dst` on the board.

        Args:
            src: path on the host.
            dst: path on the board.
        """
        self._driver.put(src, dst)

    def get(self, src: str, dst: str) -> None:
        """Copy `src` on the board to the host path `dst`.

        Args:
            src: path on the board.
            dst: path on the host.
        """
        self._driver.get(src, dst)

    def forward_remote_port(self, local: int, remote: int) -> AbstractContextManager:
        """Forward the board's port `remote` to the host's port `local`.

        Args:
            local: port on the host.
            remote: port on the board.

        Returns:
            labgrid's forwarding context manager.
        """
        return self._driver.forward_remote_port(remoteport=remote, localport=local)

    def connect(self) -> None:
        """Activate the board's SSHDriver."""
        self._target.activate(self._driver)

    def disconnect(self) -> None:
        """Deactivate the board's SSHDriver."""
        self._target.deactivate(self._driver)

    def boot_variables(self) -> tuple[list[str], dict[str, int]]:
        """BOOT_ORDER as a list of slot bootnames, and each slot's BOOT_x_LEFT, from `fw_printenv`.

        Returns:
            The boot order, and the attempts left per bootname.
        """
        stdout = self.run(self.BOOT_VARIABLES_CMD, check=True)[0]
        variables = dict(line.split("=", 1) for line in stdout)
        left = {name: int(variables[f"BOOT_{name}_LEFT"]) for name in ("A", "B")}
        return variables["BOOT_ORDER"].split(), left

    def snapshot(self) -> dict:
        """What the next boot and the running build are, read from the board.

        Returns:
            The raw `boot_variables` text, the parsed `rauc_status`, the `boot_id` and the `commit`.
        """
        return {
            "boot_variables": self.read(self.BOOT_VARIABLES_CMD),
            "rauc_status": json.loads(self.read("rauc status --detailed --output-format=json")),
            "boot_id": self.read(self.BOOT_ID_CMD),
            "commit": self.commit(),
        }

    def commit(self) -> str:
        """The meta-wisekiosk commit the board's image was built from.

        Returns:
            The commit named by the meta-wisekiosk line of /etc/buildinfo.

        Raises:
            AssertionError: /etc/buildinfo cannot be read, or carries no meta-wisekiosk line.
        """
        stdout = self.read("cat /etc/buildinfo", timeout=None).splitlines()
        line = next((entry for entry in stdout if entry.split()[:2] == ["meta-wisekiosk", "="]), None)
        assert line is not None, f"no meta-wisekiosk layer line in buildinfo:\n{chr(10).join(stdout)}"
        return line.split()[2].rsplit(":", 1)[-1]

    def sha256(self, path: str) -> str | None:
        """The sha256 of the file `path` on the board.

        Args:
            path: path on the board.

        Returns:
            The hash, or None if `sha256sum` returns nonzero (the file is missing or unreadable).
        """
        stdout, _stderr, returncode = self.run(f"sha256sum {path}")
        if returncode != 0:
            return None
        return stdout[0].split()[0]

    def page(self) -> tuple[float, bool, str]:
        """Fetch the WiseKiosk instance's page on the board once.

        Returns:
            The board's uptime at the fetch, whether it served an HTML page (return code 0 with
            `<html` in the output), and the stdout and stderr joined by newlines, stripped.

        Raises:
            ExecutionError: the session failed, as `timed` raises.
            subprocess.TimeoutExpired: the fetch ran past its timeout.
        """
        uptime, stdout, stderr, returncode = self.timed(self._PAGE_FETCH_CMD, timeout=self._PAGE_TIMEOUT_SECONDS)
        output = "\n".join(stdout + stderr).strip()
        return uptime, returncode == 0 and "<html" in output, output

    def wait_for_page(self) -> None:
        """Poll until the page serves an HTML document.

        Raises:
            AssertionError: the page did not serve within `_PAGE_WAIT_SECONDS`.
        """
        served_s, _ = poll(lambda: self.page()[1] or None, bool, self._PAGE_WAIT_SECONDS, every=self._PAGE_POLL_SECONDS)
        assert served_s is not None, f"the page did not serve within {self._PAGE_WAIT_SECONDS} s"

    def until_up(self, since: float) -> tuple[float | None, tuple[bool, bool] | None]:
        """Poll until the browser is running and the page is served.

        Args:
            since: the `time.monotonic()` instant the time counts from.

        Returns:
            The seconds from `since` until the instance was up (None if it was not within
            `GIVE_UP_SECONDS`), and the last read as (browser running, page served).
        """
        return poll(lambda: (self.run("pgrep -x surf")[2] == 0, self.page()[1]), all, GIVE_UP_SECONDS, since=since)

    def install_image(self) -> None:
        """Install the built image on the board with `just kiosk-ota`.

        Raises:
            subprocess.CalledProcessError: `just kiosk-ota` exits nonzero.
        """
        subprocess.run(["just", "kiosk-ota", self.host], check=True)

    def restart(self) -> None:
        """Restart the board with `systemctl reboot` and reconnect the SSHDriver in the new boot.

        Raises:
            AssertionError: the board did not answer in a new boot within `_REBOOT_WAIT_SECONDS`.
        """
        self.restart_by("systemctl reboot", wait_seconds=self._REBOOT_WAIT_SECONDS)

    def reconnect(self) -> None:
        """Connect the SSHDriver, retrying every 1 s until the board answers.

        Waits through a reboot in progress.

        Raises:
            AssertionError: the board did not answer within `_RESTART_WAIT_SECONDS`.
        """
        answered_s, _ = poll(lambda: self._answer(self.BOOT_ID_CMD), bool, self._RESTART_WAIT_SECONDS)
        assert answered_s is not None, f"the board did not answer within {self._RESTART_WAIT_SECONDS} s"

    def fresh_ssh_argv(self, *options: str) -> list[str]:
        """The argv of an ssh to the board over its own connection, short of the remote command.

        Carries no control master: the connection is its own TCP session with its own
        authentication, whatever the host's ssh config says.

        Args:
            *options: further `-o` options, each as `Name=value`.

        Returns:
            `ssh`, the shared and given options, then `host`; the caller appends the remote command.
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

    def restart_by(self, cmd: str, wait_seconds: float = _RESTART_WAIT_SECONDS, boot_cmd: str = BOOT_ID_CMD) -> None:
        """Take the board down with `cmd` over a one-shot ssh, then reconnect in a new boot.

        Polls every 1 s, so a test can time the restart. It disconnects the SSHDriver before
        sending `cmd`, while the board is still up. If the board never answers in a new boot, the
        SSHDriver is left as the last attempt left it, connected if the last connect succeeded.

        Args:
            cmd: the command that restarts or crashes the board.
            wait_seconds: how long to wait for the board to answer in a new boot.
            boot_cmd: prints a value that differs in each new boot.

        Raises:
            AssertionError: the opening `boot_cmd` read returned nonzero, or the board did not
                answer in a new boot within `wait_seconds`; the message carries how the ssh that
                sent `cmd` ended.
            subprocess.TimeoutExpired: reading `boot_cmd` before `cmd` ran past its timeout.
        """
        old_boot = self.read(boot_cmd)
        self.disconnect()
        try:
            sent = subprocess.run(
                [
                    *self.fresh_ssh_argv("ConnectTimeout=10", "ServerAliveInterval=2", "ServerAliveCountMax=3"),
                    cmd,
                ],
                capture_output=True,
                text=True,
                timeout=self._FAULT_SSH_TIMEOUT_SECONDS,
            )
            sent_as = f"rc {sent.returncode}, stderr {sent.stderr.strip()[-200:]!r}"
        except subprocess.TimeoutExpired:
            sent_as = f"timed out after {self._FAULT_SSH_TIMEOUT_SECONDS} s"
        back_s, _ = poll(lambda: self._answer(boot_cmd), lambda boot: boot != old_boot, wait_seconds)
        assert back_s is not None, (
            f"the board did not answer in a new boot within {wait_seconds} s; "
            f"the ssh that sent {cmd!r} ended with {sent_as}"
        )

    def _answer(self, boot_cmd: str) -> str | None:
        """Reconnect the SSHDriver and read `boot_cmd` once.

        Args:
            boot_cmd: prints a value that differs in each boot.

        Returns:
            The first line of its output, stripped; None if the board did not connect or the
            command returned nonzero or printed nothing.
        """
        self.disconnect()
        try:
            self.connect()
        except Exception:  # labgrid's activation timeout is a bare Exception
            return None
        stdout, _stderr, returncode = self.run(boot_cmd)
        return stdout[0].strip() if returncode == 0 and stdout else None
