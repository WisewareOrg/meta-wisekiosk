"""The board under test as the tests drive it: its shell, page, boot state, image install and restarts."""

import json
import os
import subprocess
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

import pytest
from labgrid import Target
from labgrid.binding import StateError
from labgrid.driver.exception import ExecutionError
from tenacity import Retrying, retry_if_exception_type, retry_if_result, stop_after_delay, wait_fixed

# the power_cut fixture's callable: cut, restore, reconnect; returns when power returned
PowerCut = Callable[[], float]


class Board:
    """The board under test: its remote shell, page, commit, image install and restarts.

    Wraps the target's SSHDriver and carries every call to it, so no test reaches the driver. Every
    other method is a read or a restart the tests make; a read that needs a clock stamp takes the
    board's uptime from the same command (`timed`).

    Attributes:
        host: `user@address` of the board, as the `just kiosk-*` recipes take it.
        last_up: the last (browser running, page served) read of `until_up`, None if it read nothing.
        CONFIG_PATH: the live configuration file on the board.
        DEFAULT_CONFIG_PATH: the image's default configuration, which the board reseeds the live file
            from when it holds none.
        BOOT_ID_CMD: prints the kernel's boot id, which differs in each boot.
        BOOT_VARIABLES_CMD: prints BOOT_ORDER and each slot's BOOT_x_LEFT as name=value lines.
        ERRORS: what a read of the board raises when the board does not answer; a wait retries these.
        GIVE_UP_SECONDS: how long a test waits for the board; past every bound, so the record still
            carries the time it took.
    """

    host: str
    last_up: tuple[bool, bool] | None = None
    CONFIG_PATH = "/data/config/config.json"
    DEFAULT_CONFIG_PATH = "/usr/share/wisekiosk/config.example.json"
    BOOT_ID_CMD = "cat /proc/sys/kernel/random/boot_id"
    BOOT_VARIABLES_CMD = "fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT"
    ERRORS = (ExecutionError, StateError, subprocess.TimeoutExpired)
    GIVE_UP_SECONDS = 180
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
        self.last_up = None
        self._driver = target.get_driver("SSHDriver")
        service = target.get_resource("NetworkService")
        self.host = f"{service.username}@{service.address}"

    def wait[T](
        self,
        read: Callable[[], T | None],
        done: Callable[[T], object],
        within: float,
        every: float = 1,
        since: float | None = None,
    ) -> tuple[float | None, T | None]:
        """Call `read` every `every` seconds until `done` accepts its value, or `within` seconds pass.

        A read that raises one of `ERRORS`, or returns None, is a failed read: `done` is not asked.
        The bound is checked after each failed read, so the last read may land one read past it.

        Args:
            read: reads the board once; None means no answer yet.
            done: whether a read value ends the wait.
            within: seconds from `since` after which the wait gives up.
            every: seconds slept between reads.
            since: the `time.monotonic()` instant the wait counts from; now when None.

        Returns:
            The seconds from `since` to the read `done` accepted, rounded to 0.1 s (None if it gave
            up), and the final read: that value, or on a give-up the last attempt's value, None if it
            raised or returned None.
        """
        since = time.monotonic() if since is None else since
        value = Retrying(
            stop=stop_after_delay(within - (time.monotonic() - since)),
            wait=wait_fixed(every),
            retry=retry_if_exception_type(self.ERRORS)
            | retry_if_result(lambda value: value is None or not done(value)),
            retry_error_callback=lambda state: None if state.outcome.failed else state.outcome.result(),
        )(read)
        return (round(time.monotonic() - since, 1) if value is not None and done(value) else None), value

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
            ExecutionError: stdout carries no uptime line, so the session failed; a wait takes it as
                a failed read.
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
        """
        uptime, stdout, stderr, returncode = self.timed(self._PAGE_FETCH_CMD, timeout=self._PAGE_TIMEOUT_SECONDS)
        output = "\n".join(stdout + stderr).strip()
        return uptime, returncode == 0 and "<html" in output, output

    def wait_for_page(self) -> None:
        """Wait until the page serves an HTML document."""
        served_s, _ = self.wait(
            lambda: self.page()[1] or None, bool, self._PAGE_WAIT_SECONDS, every=self._PAGE_POLL_SECONDS
        )
        assert served_s is not None, f"the page did not serve within {self._PAGE_WAIT_SECONDS} s"

    def until_up(self, since: float) -> tuple[float | None, tuple[bool, bool] | None]:
        """Wait until the browser is running and the page is served.

        Resets `last_up` first, so an earlier wait's read never stands in for this one's.

        Args:
            since: the `time.monotonic()` instant the time counts from.

        Returns:
            The seconds from `since` until the instance was up (None if it was not within
            `GIVE_UP_SECONDS`), and `last_up`: the last read as (browser running, page served), None if
            no read succeeded.
        """
        self.last_up = None
        up_s, _ = self.wait(self._up, all, self.GIVE_UP_SECONDS, since=since)
        return up_s, self.last_up

    def _up(self) -> tuple[bool, bool]:
        """Read once whether the browser is running and the page is served, and keep it in `last_up`.

        Returns:
            Whether `pgrep -x surf` found the browser, and whether the page served.
        """
        self.last_up = (self.run("pgrep -x surf")[2] == 0, self.page()[1])
        return self.last_up

    def bind(self, request: pytest.FixtureRequest, src: str | os.PathLike[str], path: str) -> None:
        """Bind-mount a copy of the host file `src` over `path` on the board, until `request`'s teardown.

        Each undo is registered once its step has succeeded, so teardown unmounts, then removes the
        copy.

        Args:
            request: registers each step's undo.
            src: the file on the host; its copy on the board is `/tmp/kiosk-<its name>`.
            path: the file on the board to mount it over; a stale mount a dead run left there is
                unmounted first.
        """
        copy = f"/tmp/kiosk-{Path(src).name}"
        self.put(str(src), copy)
        request.addfinalizer(lambda: self.run(f"rm -f {copy}", check=True))
        self.unmount_if_mounted(path)
        self.run(f"mount --bind {copy} {path}", check=True)
        request.addfinalizer(lambda: self.unmount_if_mounted(path))

    def run_later(self, request: pytest.FixtureRequest, unit: str, delay: float, cmd: str) -> None:
        """Start `cmd` on the board in `delay` seconds as the transient timer `unit`.

        What a dead run left of the unit is cleared first, and the timer is stopped again at
        `request`'s teardown.

        Args:
            request: registers the undo.
            unit: the transient unit's name.
            delay: seconds from now to the start.
            cmd: the command line `systemd-run` runs.
        """
        units = f"{unit}.timer {unit}.service"
        undo = f"systemctl stop {units}; systemctl reset-failed {units}"
        self.run(undo)
        self.run(f"systemd-run --unit={unit} --on-active={delay} --timer-property=AccuracySec=100ms {cmd}", check=True)
        request.addfinalizer(lambda: self.run(undo))

    def install_image(self) -> None:
        """Install the built image on the board with `just kiosk-ota`."""
        subprocess.run(["just", "kiosk-ota", self.host], check=True)

    def restart(self) -> None:
        """Restart the board with `systemctl reboot` and reconnect the SSHDriver in the new boot."""
        self.restart_by("systemctl reboot", wait_seconds=self._REBOOT_WAIT_SECONDS)

    def reconnect(self) -> None:
        """Connect the SSHDriver, retrying every 1 s until the board answers.

        Waits through a reboot in progress.
        """
        self._wait_for_boot(self._RESTART_WAIT_SECONDS, self.BOOT_ID_CMD)

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

        Attempts a reconnect every 1 s, so a test can time the restart. It disconnects the SSHDriver before
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
        try:
            self._wait_for_boot(wait_seconds, boot_cmd, old_boot)
        except AssertionError as error:
            raise AssertionError(f"{error}; the ssh that sent {cmd!r} ended with {sent_as}") from None

    def _wait_for_boot(self, within: float, boot_cmd: str, old: str | None = None) -> None:
        """Reconnect the SSHDriver, one attempt a second, until `boot_cmd` reads.

        Each attempt disconnects, connects and reads `boot_cmd`; with `old` given, a read equal to it
        is the old boot and the attempt fails.

        Args:
            within: seconds after which the wait gives up.
            boot_cmd: prints a value that differs in each boot.
            old: the value `boot_cmd` printed before the restart, or None for no such value.

        Raises:
            AssertionError: the board did not answer, in a new boot when `old` is given, within
                `within` seconds.
        """
        try:
            for attempt in Retrying(stop=stop_after_delay(within), wait=wait_fixed(1), reraise=True):
                with attempt:
                    self.disconnect()
                    self.connect()
                    assert self.read(boot_cmd) != old, "the board is still in the old boot"
        except Exception as error:  # labgrid's activation timeout is a bare Exception
            kind = " in a new boot" if old is not None else ""
            raise AssertionError(f"the board did not answer{kind} within {within} s") from error
