"""The board under test, for one test: its parts, and an undo of everything the test changed."""

import contextlib
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
from labgrid import Target
from labgrid.binding import StateError
from labgrid.driver.exception import ExecutionError
from tenacity import Retrying, retry_if_exception_type, retry_if_result, stop_after_delay, wait_fixed

from board.app import App


class InstanceState(NamedTuple):
    """One read of whether the instance is up: the browser running and the page served.

    Attributes:
        browser_running: `pgrep -x surf` found the browser.
        page_served: the page served an HTML document.
    """

    browser_running: bool
    page_served: bool


class Board:
    """The board under test, for one test: its shell, its parts, and an undo of what the test changed.

    Every call to the board goes through its SSHDriver, which labgrid keeps open for the run, so a
    new `Board` per test opens no new connection. A part or a test that changes the board registers
    the undo on `cleanup`, which the target suite's conftest closes when the test ends.

    Attributes:
        app: the WiseKiosk app on the board.
        cleanup: undoes, last first, what the test changed on the board.
        host: `user@address` of the board, as the `just kiosk-*` recipes take it.
        last_instance_state: the last read of `seconds_until_instance_up`, None before one.
        BOOT_ID_CMD: prints the kernel's boot id, which differs in each boot.
        ERRORS: what a read of the board raises when the board does not answer; `poll` retries these.
        GIVE_UP_SECONDS: how long a test waits for the board; past every bound, so the record still
            carries the time it took.
        PAGE_FETCH_CMD: fetches the WiseKiosk instance's page on the board to stdout; busybox wget
            returns 0 only on 2xx.
        PAGE_ATTEMPT_TIMEOUT_SECONDS: the longest one page fetch may take.
    """

    app: App
    cleanup: contextlib.ExitStack
    host: str
    last_instance_state: InstanceState | None
    BOOT_ID_CMD = "cat /proc/sys/kernel/random/boot_id"
    ERRORS = (ExecutionError, StateError, subprocess.TimeoutExpired)
    GIVE_UP_SECONDS = 180
    PAGE_FETCH_CMD = "wget -q -O- http://127.0.0.1:8080/"
    PAGE_ATTEMPT_TIMEOUT_SECONDS = 10
    _COMMAND_TIMEOUT_SECONDS = 10
    _PAGE_WAIT_SECONDS = 60
    _PAGE_POLL_SECONDS = 2
    _RESTART_WAIT_SECONDS = 180
    _FAULT_SSH_TIMEOUT_SECONDS = 30
    _POWER_OFF_SECONDS = 10

    def __init__(self, target: Target) -> None:
        """Bind to the target's SSHDriver and NetworkService, and build the board's parts.

        Args:
            target: names the board's SSHDriver, NetworkService and ExternalPowerDriver.
        """
        self._target = target
        self._ssh = target.get_driver("SSHDriver")
        service = target.get_resource("NetworkService")
        self.host = f"{service.username}@{service.address}"
        self.cleanup = contextlib.ExitStack()
        self.last_instance_state = None
        self.app = App(self)

    def run(
        self, cmd: str, check: bool = False, timeout: float | None = _COMMAND_TIMEOUT_SECONDS
    ) -> tuple[list[str], list[str], int]:
        """Run `cmd` on the board.

        Args:
            cmd: the command to run.
            check: assert the command returned 0.
            timeout: forwarded to the SSHDriver; None means no timeout.

        Returns:
            The stdout lines, the stderr lines and the return code.
        """
        stdout, stderr, returncode = self._ssh.run(cmd, timeout=timeout)
        if check:
            output = stdout + stderr
            assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
        return stdout, stderr, returncode

    def read(self, cmd: str, timeout: float | None = _COMMAND_TIMEOUT_SECONDS) -> str:
        """Run `cmd` on the board, assert it returned 0, and return its stdout.

        Args:
            cmd: the command to run.
            timeout: forwarded to `run`.

        Returns:
            The stdout lines joined by newlines, stripped.
        """
        return "\n".join(self.run(cmd, check=True, timeout=timeout)[0]).strip()

    def run_with_uptime(
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
            ExecutionError: stdout carries no uptime line, so the session failed; `poll` takes it as
                a failed read.
        """
        stdout, stderr, returncode = self.run(f"cat /proc/uptime; {cmd}", check=check, timeout=timeout)
        try:
            uptime = float(stdout[0].split()[0])
        except (IndexError, ValueError):
            raise ExecutionError(cmd, stdout, stderr) from None
        return uptime, stdout[1:], stderr, returncode

    def put(self, src: str, dst: str) -> None:
        """Copy the host file `src` to `dst` on the board.

        Args:
            src: path on the host.
            dst: path on the board.
        """
        self._ssh.put(src, dst)

    def unmount_if_mounted(self, path: str) -> None:
        """Unmount `path` on the board if it is a mount point; a path that is not one is fine.

        Args:
            path: the mount point on the board.
        """
        self.run(f"if grep -q ' {path} ' /proc/self/mountinfo; then umount {path}; fi", check=True)

    def bind_over(self, src: str | os.PathLike[str], path: str) -> None:
        """Bind-mount a copy of the host file `src` over `path` on the board, until the test ends.

        Each undo is registered on `cleanup` once its step has succeeded, so the copy is unmounted,
        then removed.

        Args:
            src: the file on the host; its copy on the board is `/tmp/kiosk-<its name>`.
            path: the file on the board to mount it over; a stale mount a dead run left there is
                unmounted first.
        """
        copy = f"/tmp/kiosk-{Path(src).name}"
        self.put(str(src), copy)
        self.cleanup.callback(self.run, f"rm -f {copy}", check=True)
        self.unmount_if_mounted(path)
        self.run(f"mount --bind {copy} {path}", check=True)
        self.cleanup.callback(self.unmount_if_mounted, path)

    def run_later(self, unit: str, delay: float, cmd: str) -> None:
        """Start `cmd` on the board in `delay` seconds as the transient timer `unit`, until the test ends.

        What a dead run left of the unit is cleared first, and the timer is stopped again when the
        test ends.

        Args:
            unit: the transient unit's name.
            delay: seconds from now to the start.
            cmd: the command line `systemd-run` runs.
        """
        units = f"{unit}.timer {unit}.service"
        stop = f"systemctl stop {units}; systemctl reset-failed {units}"
        self.run(stop)
        self.cleanup.callback(self.run, stop)
        self.run(f"systemd-run --unit={unit} --on-active={delay} --timer-property=AccuracySec=100ms {cmd}", check=True)

    def poll[T](
        self,
        read: Callable[[], T | None],
        *,
        until: Callable[[T], object],
        within: float,
        every: float = 1,
        since: float | None = None,
    ) -> tuple[float | None, T | None]:
        """Call `read` every `every` seconds until `until` accepts its value, or `within` seconds pass.

        A read that raises one of `ERRORS`, or returns None, is a failed read: `until` is not asked.
        The bound is checked after each read, so the last read may land one read past it.

        Args:
            read: reads the board once; None means no answer yet.
            until: whether a read value ends the wait.
            within: seconds from `since` after which the wait gives up.
            every: seconds slept between reads.
            since: the `time.monotonic()` instant the wait counts from; now when None.

        Returns:
            The seconds from `since` to the read `until` accepted, rounded to 0.1 s (None if it gave
            up), and the final read: that value, or on a give-up the last attempt's value, None if it
            raised or returned None.
        """
        since = time.monotonic() if since is None else since
        value = Retrying(
            stop=stop_after_delay(within - (time.monotonic() - since)),
            wait=wait_fixed(every),
            retry=retry_if_exception_type(self.ERRORS)
            | retry_if_result(lambda value: value is None or not until(value)),
            retry_error_callback=lambda state: None if state.outcome.failed else state.outcome.result(),
        )(read)
        done = value is not None and until(value)
        return (round(time.monotonic() - since, 1) if done else None), value

    def fetch_page(self, timeout: float = PAGE_ATTEMPT_TIMEOUT_SECONDS) -> tuple[int, str]:
        """Fetch the WiseKiosk instance's page on the board once.

        Args:
            timeout: forwarded to `run`.

        Returns:
            The return code, and the stdout and stderr joined by newlines, stripped.
        """
        stdout, stderr, returncode = self.run(self.PAGE_FETCH_CMD, timeout=timeout)
        return returncode, "\n".join(stdout + stderr).strip()

    @staticmethod
    def is_page(returncode: int, output: str) -> bool:
        """Whether a page fetch's return code and output are an HTML page served.

        Args:
            returncode: the fetch's return code.
            output: the fetch's stdout and stderr.

        Returns:
            True if the fetch returned 0 with `<html` in its output.
        """
        return returncode == 0 and "<html" in output

    def page_served(self, timeout: float = PAGE_ATTEMPT_TIMEOUT_SECONDS) -> bool:
        """Fetch the page once and say whether it served an HTML page.

        Args:
            timeout: forwarded to `fetch_page`.

        Returns:
            Whether the fetch served an HTML page; False if it timed out.
        """
        try:
            return self.is_page(*self.fetch_page(timeout=timeout))
        except subprocess.TimeoutExpired:
            return False

    def wait_for_page(self) -> None:
        """Wait until the page serves an HTML document."""
        served_s, _ = self.poll(
            lambda: self.page_served() or None,
            until=bool,
            within=self._PAGE_WAIT_SECONDS,
            every=self._PAGE_POLL_SECONDS,
        )
        assert served_s is not None, f"the page did not serve within {self._PAGE_WAIT_SECONDS} s"

    def seconds_until_instance_up(self, since: float) -> tuple[float | None, InstanceState | None]:
        """Wait until the instance is up: the page served and the browser running.

        Resets `last_instance_state` first, so an earlier wait's read never stands in for this one's.

        Args:
            since: the `time.monotonic()` instant the time counts from.

        Returns:
            The seconds from `since` until the instance was up (None if it was not within
            `GIVE_UP_SECONDS`), and `last_instance_state`.
        """
        self.last_instance_state = None
        up_s, _ = self.poll(self._read_instance_state, until=all, within=self.GIVE_UP_SECONDS, since=since)
        return up_s, self.last_instance_state

    def connect(self) -> None:
        """Activate the board's SSHDriver."""
        self._target.activate(self._ssh)

    def disconnect(self) -> None:
        """Deactivate the board's SSHDriver."""
        self._target.deactivate(self._ssh)

    def reconnect(self) -> None:
        """Connect the SSHDriver, one attempt a second, until the board answers; waits through a reboot."""
        self._reconnect_in_new_boot(self._RESTART_WAIT_SECONDS, self.BOOT_ID_CMD)

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

    def restart_with(self, cmd: str, within: float = _RESTART_WAIT_SECONDS, boot_cmd: str = BOOT_ID_CMD) -> float:
        """Take the board down with `cmd` over a one-shot ssh, then reconnect in a new boot.

        Attempts a reconnect every 1 s, so a test can time the restart from the returned instant. It
        disconnects the SSHDriver before sending `cmd`, while the board is still up. A time taken from
        the returned instant overstates by the boot-id read, the disconnect and the ssh connect before
        the fault lands.

        Args:
            cmd: the command that restarts or crashes the board.
            within: how long to wait for the board to answer in a new boot.
            boot_cmd: prints a value that differs in each new boot.

        Returns:
            The host `time.monotonic()` taken just before the command, the instant the recovery is
            timed from.

        Raises:
            AssertionError: the board did not answer in a new boot within `within`; the message
                carries how the ssh that sent `cmd` ended.
        """
        started = time.monotonic()
        old_boot = self.read(boot_cmd)
        self.disconnect()
        try:
            sent = subprocess.run(
                [*self.fresh_ssh_argv("ConnectTimeout=10", "ServerAliveInterval=2", "ServerAliveCountMax=3"), cmd],
                capture_output=True,
                text=True,
                timeout=self._FAULT_SSH_TIMEOUT_SECONDS,
            )
            sent_as = f"rc {sent.returncode}, stderr {sent.stderr.strip()[-200:]!r}"
        except subprocess.TimeoutExpired:
            sent_as = f"timed out after {self._FAULT_SSH_TIMEOUT_SECONDS} s"
        try:
            self._reconnect_in_new_boot(within, boot_cmd, old_boot)
        except AssertionError as error:
            raise AssertionError(f"{error}; the ssh that sent {cmd!r} ended with {sent_as}") from None
        return started

    def cut_power(self) -> tuple[float, float]:
        """Cut the board's power through the bench's switched plug, restore it, and reconnect in a new boot.

        Power is switched back on when the test ends. The run exits if the plug fails, or if the board
        answers in the same boot after the power was off.

        Returns:
            The host `time.monotonic()` at which the `on` command started (power returns no earlier,
            so a time taken from it errs high), and the seconds that command took.
        """
        power = self._target.get_driver("ExternalPowerDriver")
        self.cleanup.callback(power.on)
        old_boot_id = self.read(self.BOOT_ID_CMD)
        self.disconnect()
        try:
            power.off()
            time.sleep(self._POWER_OFF_SECONDS)
            on_began = time.monotonic()
            power.on()
        except (subprocess.CalledProcessError, OSError) as error:
            pytest.exit(f"the bench's power switch failed: {error}", returncode=2)
        on_command_s = round(time.monotonic() - on_began, 1)
        self.reconnect()
        if self.read(self.BOOT_ID_CMD) == old_boot_id:
            pytest.exit(
                f"the board answered in the same boot after {self._POWER_OFF_SECONDS} s off: "
                "the plug or its supply did not cut power",
                returncode=2,
            )
        return on_began, on_command_s

    def _read_instance_state(self) -> InstanceState:
        """Read once whether the browser is running and the page is served, into `last_instance_state`.

        A read that fails counts as the browser not running, or the page not served.

        Returns:
            The read.
        """
        try:
            browser_running = self.run("pgrep -x surf")[2] == 0
        except (ExecutionError, subprocess.TimeoutExpired):
            browser_running = False
        try:
            page_served = self.page_served()
        except ExecutionError:
            page_served = False
        self.last_instance_state = InstanceState(browser_running, page_served)
        return self.last_instance_state

    def _reconnect_in_new_boot(self, within: float, boot_cmd: str, old: str | None = None) -> None:
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
