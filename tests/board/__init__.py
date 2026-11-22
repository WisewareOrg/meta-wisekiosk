"""The board under test, for one test: its parts, and an undo of everything the test changed."""

import contextlib
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest
from labgrid import Target
from labgrid.binding import StateError
from labgrid.driver.exception import ExecutionError
from tenacity import Retrying, retry_if_exception_type, retry_if_result, stop_after_delay, wait_fixed

from board.app import App, Backend, Config, Page
from board.console import Console, Keyboard, Terminals
from board.network import Load, Network, Outage
from board.screen import Captures, Display, Screen
from board.system import Clock, Journal, Kernel, Memory, Soak, System, Timezone
from board.updates import Updates

if TYPE_CHECKING:
    from record import Record


class CommandResult(NamedTuple):
    """What one command on the board printed and returned.

    Attributes:
        stdout: the stdout lines.
        stderr: the stderr lines.
        returncode: the return code.
        uptime_s: the board's uptime just before the command, when it was asked for.
    """

    stdout: list[str]
    stderr: list[str]
    returncode: int
    uptime_s: float | None = None

    @property
    def text(self) -> str:
        """The stdout lines joined by newlines, stripped.

        Returns:
            The text.
        """
        return "\n".join(self.stdout).strip()

    @property
    def output(self) -> str:
        """The stdout lines, then the stderr lines, joined by newlines, stripped.

        Returns:
            The output.
        """
        return "\n".join(self.stdout + self.stderr).strip()


class Board:
    """The board under test, for one test: its shell, its parts, and an undo of what the test changed.

    Every call to the board goes through its SSHDriver, which labgrid keeps open for the run, so a
    new `Board` per test opens no new connection. A part or a test that changes the board registers
    the undo on `cleanup`, which the target suite's conftest closes when the test ends.

    Attributes:
        app: the WiseKiosk app on the board.
        cleanup: undoes, last first, what the test changed on the board.
        console: the board's consoles, and a keyboard attached to them.
        host: `user@address` of the board, as the `just kiosk-*` recipes take it.
        network: the board's network.
        screen: the board's screen.
        system: the board's operating system.
        updates: RAUC and the board's install path.
        BOOT_ID_CMD: prints the kernel's boot id, which differs in each boot.
        ERRORS: what a read of the board raises when the board does not answer; `poll` retries these.
        FAULT_SSH_OPTIONS: the `fresh_ssh_argv` options for an ssh that sends a fault taking the board
            down, so it gives up soon once the board stops answering.
        GIVE_UP_SECONDS: how long a test waits for the board; past every bound, so the record still
            carries the time it took.
        READ_RETRY_SECONDS: how long a read passed it as `retry_for` keeps reconnecting and retrying.
    """

    app: App
    cleanup: contextlib.ExitStack
    console: Console
    host: str
    network: Network
    screen: Screen
    system: System
    updates: Updates
    BOOT_ID_CMD = "cat /proc/sys/kernel/random/boot_id"
    ERRORS = (ExecutionError, StateError, subprocess.TimeoutExpired)
    FAULT_SSH_OPTIONS = ("ConnectTimeout=10", "ServerAliveInterval=2", "ServerAliveCountMax=3")
    GIVE_UP_SECONDS = 180
    READ_RETRY_SECONDS = 300
    _COMMAND_TIMEOUT_SECONDS = 10
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
        self.app = App(backend=Backend(self), config=Config(self), page=Page(self))
        self.screen = Screen(display=Display(self), captures=Captures(self))
        self.console = Console(terminals=Terminals(self), keyboard=Keyboard(self))
        self.system = System(
            clock=Clock(self),
            timezone=Timezone(self),
            memory=Memory(self),
            soak=Soak(self),
            kernel=Kernel(self),
            journal=Journal(self),
        )
        self.network = Network(outage=Outage(self), load=Load(self))
        self.updates = Updates(self)

    def __enter__(self) -> "Board":
        """Use the board for a span other than one test.

        Returns:
            The board.
        """
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Undo, last first, what was changed on the board during the span.

        Args:
            *exc_info: the exception that ended the span, if any.
        """
        self.cleanup.close()

    def run(
        self,
        cmd: str,
        *,
        check: bool = False,
        timeout: float | None = _COMMAND_TIMEOUT_SECONDS,
        retry_for: float | None = None,
        with_uptime: bool = False,
    ) -> CommandResult:
        """Run `cmd` on the board.

        With `retry_for`, a call that raises one of `ERRORS` reconnects and runs again until
        `retry_for` seconds have passed, then raises the last error unchanged; only the call to the
        board is retried, never the check or the uptime parse.

        Args:
            cmd: the command to run.
            check: assert the command returned 0.
            timeout: forwarded to the SSHDriver; None means no timeout.
            retry_for: how long to keep retrying a call that raises one of `ERRORS`; None runs it once.
            with_uptime: stamp the result with the board's uptime, read in the same command just before
                `cmd`.

        Returns:
            The command's stdout lines (after the uptime line when `with_uptime` is set), stderr lines,
            return code and, when `with_uptime` is set, the board's uptime in seconds.

        Raises:
            ExecutionError: `with_uptime` is set and stdout carries no uptime line, so the session failed;
                `poll` takes it as a failed read.
        """
        ssh_run = self._ssh.run
        if retry_for is not None:
            ssh_run = Retrying(
                stop=stop_after_delay(retry_for),
                retry=retry_if_exception_type(self.ERRORS),
                before_sleep=lambda _state: self._reconnect_if_it_answers(),
                reraise=True,
            ).wraps(self._ssh.run)
        stdout, stderr, returncode = ssh_run(f"cat /proc/uptime; {cmd}" if with_uptime else cmd, timeout=timeout)
        if check:
            output = stdout + stderr
            assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
        if not with_uptime:
            return CommandResult(stdout, stderr, returncode)
        try:
            uptime = float(stdout[0].split()[0])
        except (IndexError, ValueError):
            raise ExecutionError(cmd, stdout, stderr) from None
        return CommandResult(stdout[1:], stderr, returncode, uptime)

    def put(self, src: str, dst: str) -> None:
        """Copy the host file `src` to `dst` on the board.

        Args:
            src: path on the host.
            dst: path on the board.
        """
        self._ssh.put(src, dst)

    def forward_remote_port(self, local: int, remote: int) -> contextlib.AbstractContextManager:
        """Forward the board's port `remote` to the host's port `local`.

        Args:
            local: port on the host.
            remote: port on the board.

        Returns:
            labgrid's forwarding context manager.
        """
        return self._ssh.forward_remote_port(remoteport=remote, localport=local)

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

    def connect(self) -> None:
        """Activate the board's SSHDriver."""
        self._target.activate(self._ssh)

    def disconnect(self) -> None:
        """Deactivate the board's SSHDriver."""
        self._target.deactivate(self._ssh)

    def get(self, src: str, dst: str) -> None:
        """Copy `src` on the board to the host path `dst`.

        Args:
            src: path on the board.
            dst: path on the host.
        """
        self._ssh.get(src, dst)

    def reboot(self) -> None:
        """Reboot the board through `just kiosk-reboot`, which waits up to 300 s for a new boot, then reconnect."""
        subprocess.run(["just", "kiosk-reboot", self.host], check=True)
        self.disconnect()
        self.connect()

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
        old_boot = self.run(boot_cmd, check=True).text
        self.disconnect()
        try:
            sent = subprocess.run(
                [*self.fresh_ssh_argv(*self.FAULT_SSH_OPTIONS), cmd],
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

    def cut_power(self, record: "Record") -> float:
        """Cut the board's power through the bench's switched plug, restore it, and reconnect in a new boot.

        Records how long the `on` command took as `power_on_command_s`, before the reconnect, so a
        reconnect that fails still leaves it in the record. Power is switched back on when the test
        ends. The run exits if the plug fails, or if the board answers in the same boot after the
        power was off.

        Args:
            record: the test's record.

        Returns:
            The host `time.monotonic()` at which the `on` command started; power returns no earlier,
            so a time taken from it errs high.
        """
        power = self._target.get_driver("ExternalPowerDriver")
        self.cleanup.callback(power.on)
        old_boot_id = self.system.kernel.boot_id()
        self.disconnect()
        try:
            power.off()
            time.sleep(self._POWER_OFF_SECONDS)
            on_began = time.monotonic()
            power.on()
        except (subprocess.CalledProcessError, OSError) as error:
            pytest.exit(f"the bench's power switch failed: {error}", returncode=2)
        record(power_on_command_s=round(time.monotonic() - on_began, 1))
        self.reconnect()
        if self.system.kernel.boot_id() == old_boot_id:
            pytest.exit(
                f"the board answered in the same boot after {self._POWER_OFF_SECONDS} s off: "
                "the plug or its supply did not cut power",
                returncode=2,
            )
        return on_began

    def _reconnect_if_it_answers(self) -> None:
        """Reconnect the SSHDriver, and carry on if the board does not answer in time."""
        with contextlib.suppress(AssertionError):
            self.reconnect()

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
                    assert self.run(boot_cmd, check=True).text != old, "the board is still in the old boot"
        except Exception as error:  # labgrid's activation timeout is a bare Exception
            kind = " in a new boot" if old is not None else ""
            raise AssertionError(f"the board did not answer{kind} within {within} s") from error
