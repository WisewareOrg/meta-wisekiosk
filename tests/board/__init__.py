"""The board under test, for one test: its parts, and an undo of everything the test changed."""

import contextlib
import itertools
import os
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple

import pytest
from labgrid import Target
from labgrid.binding import StateError
from labgrid.driver.exception import ExecutionError
from tenacity import Retrying, retry_if_exception_type, retry_if_result, stop_after_delay, wait_fixed

from board.app import App
from board.app.inspector import NoPageError
from board.console import Console
from board.mouse import Mouse
from board.network import Network
from board.screen import Screen
from board.system import System
from board.updates import Updates


class CommandResult(NamedTuple):
    """What one command on the board printed and returned.

    Attributes:
        stdout: the stdout lines.
        stderr: the stderr lines.
        returncode: the return code.
    """

    stdout: list[str]
    stderr: list[str]
    returncode: int

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
        console: the board's consoles.
        host: `user@address` of the board, as the `just kiosk-*` recipes take it.
        mouse: a mouse attached to the board.
        network: the board's network.
        screen: the board's screen.
        system: the board's operating system.
        updates: RAUC and the board's install path.
        BOOT_ID_CMD: prints the kernel's boot id, which differs in each boot.
        ERRORS: what a read of the board raises when the board, or its page, does not answer;
            `seconds_until` takes these as a read that does not hold.
        FAULT_SSH_OPTIONS: the `fresh_ssh_argv` options for an ssh that sends a fault taking the board
            down, so it gives up soon once the board stops answering.
        GIVE_UP_SECONDS: how long a wait for the board lasts; past every bound, so a slow board fails on
            its bound rather than on the wait.
        READ_RETRY_SECONDS: how long a read passed it as `retry_for` keeps reconnecting and retrying.
    """

    app: App
    cleanup: contextlib.ExitStack
    console: Console
    host: str
    mouse: Mouse
    network: Network
    screen: Screen
    system: System
    updates: Updates
    BOOT_ID_CMD = "cat /proc/sys/kernel/random/boot_id"
    ERRORS = (ExecutionError, StateError, subprocess.TimeoutExpired, NoPageError)
    FAULT_SSH_OPTIONS = ("ConnectTimeout=10", "ServerAliveInterval=2", "ServerAliveCountMax=3")
    GIVE_UP_SECONDS = 180
    READ_RETRY_SECONDS = 300
    _COMMAND_TIMEOUT_SECONDS = 10
    # a restart into a newly installed slot can take its first boot's longer start
    _RESTART_WAIT_SECONDS = 300
    _FAULT_SSH_TIMEOUT_SECONDS = 30
    _POWER_OFF_SECONDS = 10

    def __init__(self, target: Target, fixtures: Callable[[str], object] | None = None) -> None:
        """Bind to the target's SSHDriver and NetworkService, and build the board's parts.

        Args:
            target: names the board's SSHDriver, NetworkService and ExternalPowerDriver.
            fixtures: returns a pytest fixture's value by name, for what a part reaches on demand; the
                target suite's test boards have it, a board a fixture opens for itself does not.
        """
        self._fixtures = fixtures
        self._target = target
        self._ssh = target.get_driver("SSHDriver")
        service = target.get_resource("NetworkService")
        self.host = f"{service.username}@{service.address}"
        self.cleanup = contextlib.ExitStack()
        self.app = App(self)
        self.screen = Screen(self)
        self.console = Console(self)
        self.mouse = Mouse(self)
        self.system = System(self)
        self.network = Network(self)
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

    def fixture(self, name: str) -> object:
        """A pytest fixture's value, by name, for what a part reaches on demand, such as the run's bundles.

        Args:
            name: the fixture's name.

        Returns:
            Its value.

        Raises:
            LookupError: this board was built without the run's fixtures.
        """
        if self._fixtures is None:
            raise LookupError(f"this Board was built without the run's fixtures, so it cannot reach {name!r}")
        return self._fixtures(name)

    def run(
        self,
        cmd: str,
        *,
        check: bool = False,
        timeout: float | None = _COMMAND_TIMEOUT_SECONDS,
        retry_for: float | None = None,
    ) -> CommandResult:
        """Run `cmd` on the board.

        With `retry_for`, a call that raises one of `ERRORS` reconnects and runs again until
        `retry_for` seconds have passed, then raises the last error unchanged; only the call to the
        board is retried, never the check. A reconnect between tries can itself wait up to
        `_RESTART_WAIT_SECONDS`, so the call can take that much longer than `retry_for`.

        Args:
            cmd: the command to run.
            check: assert the command returned 0.
            timeout: forwarded to the SSHDriver; None means no timeout.
            retry_for: how long to keep retrying a call that raises one of `ERRORS`; None runs it once.

        Returns:
            The command's stdout lines, stderr lines and return code.
        """
        ssh_run = self._ssh.run
        if retry_for is not None:
            ssh_run = Retrying(
                stop=stop_after_delay(retry_for),
                retry=retry_if_exception_type(self.ERRORS),
                before_sleep=lambda _state: self._reconnect_if_it_answers(),
                reraise=True,
            ).wraps(self._ssh.run)
        stdout, stderr, returncode = ssh_run(cmd, timeout=timeout)
        if check:
            output = stdout + stderr
            assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
        return CommandResult(stdout, stderr, returncode)

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

    @contextlib.contextmanager
    def forward_local_port(self, remote: int) -> Iterator[int]:
        """Forward a port of the host to the board's port `remote`.

        Args:
            remote: port on the board.

        Yields:
            int: the host's port.

        Raises:
            ExecutionError: the connection to the board is gone.
        """
        with contextlib.ExitStack() as forwarding:
            try:
                port = forwarding.enter_context(self._ssh.forward_local_port(remote))
            except subprocess.CalledProcessError as error:
                raise ExecutionError(f"the port was not forwarded: {error}") from error
            yield port

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

    def boot_id(self, retry_for: float | None = None) -> str:
        """Read the kernel's boot id, which differs in each boot.

        Args:
            retry_for: how long to retry through a dropped session, as `run` takes it; None reads once.

        Returns:
            The boot id.
        """
        return self.run(self.BOOT_ID_CMD, check=True, retry_for=retry_for).text

    def uptime_s(self, retry_for: float | None = None) -> float:
        """Read the board's uptime.

        Args:
            retry_for: how long to retry through a dropped session, as `run` takes it; None reads once.

        Returns:
            The uptime, in seconds.
        """
        return float(self.run("cat /proc/uptime", check=True, retry_for=retry_for).text.split()[0])

    def opens_a_shell(self) -> bool:
        """Whether a remote shell of its own opens on the board, apart from the connection the tests use.

        Returns:
            True if a command ran in it.
        """
        return self.in_a_new_shell("true") is not None

    def in_a_new_shell(self, cmd: str) -> str | None:
        """Run `cmd` in a remote shell of its own on the board, apart from the connection the tests use.

        Args:
            cmd: the command.

        Returns:
            Its output, stripped; None if no shell opened or the command failed.
        """
        try:
            ssh = subprocess.run(
                [*self.fresh_ssh_argv("ConnectTimeout=5"), cmd], capture_output=True, text=True, timeout=10
            )
        except subprocess.TimeoutExpired:
            return None
        return ssh.stdout.strip() if ssh.returncode == 0 else None

    def restart(self) -> float:
        """Restart the board, and reconnect once it is up in a new boot.

        Returns:
            The host `time.monotonic()` taken before the restart was asked for.
        """
        return self.restart_with("systemctl reboot")

    def crash_kernel(self) -> float:
        """Crash the kernel, so that nothing on the board runs, and reconnect once it has restarted by itself.

        Returns:
            The host `time.monotonic()` taken before the crash was sent.
        """
        return self.restart_with("echo c > /proc/sysrq-trigger")

    def cut_power(self) -> float:
        """Cut the board's power through the bench's switched plug, restore it, and reconnect in a new boot.

        Power is switched back on when the test ends. The run exits if the plug fails, or if the board
        answers in the same boot after the power was off.

        Returns:
            The host `time.monotonic()` at which the `on` command started; power returns no earlier,
            so a time taken from it errs high.
        """
        power = self._target.get_driver("ExternalPowerDriver")
        self.cleanup.callback(power.on)
        old_boot_id = self.boot_id()
        self.disconnect()
        try:
            power.off()
            time.sleep(self._POWER_OFF_SECONDS)
            on_began = time.monotonic()
            power.on()
        except (subprocess.CalledProcessError, OSError) as error:
            pytest.exit(f"the bench's power switch failed: {error}", returncode=2)
        self.reconnect()
        if self.boot_id() == old_boot_id:
            pytest.exit(
                f"the board answered in the same boot after {self._POWER_OFF_SECONDS} s off: "
                "the plug or its supply did not cut power",
                returncode=2,
            )
        return on_began

    def seconds_until(self, condition: Callable[[], object], *, since: float | None = None, reads: int = 1) -> float:
        """Read `condition` about once a second until it holds on `reads` reads in a row.

        A read that raises one of `ERRORS` does not hold. An assertion fails if the streak did not begin within
        `GIVE_UP_SECONDS` of `since`.

        Args:
            condition: one read of the board; holds when truthy. A give-up names it by its qualified name,
                or its function's for a `functools.partial`.
            since: the host `time.monotonic()` instant the time counts from; now when None.
            reads: how many reads in a row it must hold on.

        Returns:
            The seconds from `since` to the end of the streak's first read, to 0.1 s.
        """
        since = time.monotonic() if since is None else since
        streak: list[float] = []

        def read() -> int:
            """Read `condition` once, stamped with the read's end, extending the streak or ending it.

            Returns:
                How many reads in a row have held.
            """
            nonlocal streak
            streak = [*streak, time.monotonic()] if self._holds(condition) else []
            return len(streak)

        held = self._each_second(
            read, until=lambda held: held >= reads, within=self.GIVE_UP_SECONDS - (time.monotonic() - since)
        )
        assert held >= reads, f"{self._name(condition)} did not hold within {self.GIVE_UP_SECONDS} s"
        return round(streak[0] - since, 1)

    def wait_for[T](self, read: Callable[[], T | None]) -> T:
        """Read about once a second until a read returns a value, and return that value.

        A read that raises one of `ERRORS`, or returns None, has no value. An assertion fails if none
        came within `GIVE_UP_SECONDS`.

        Args:
            read: one read of the board; None when what it waits for is not there yet.

        Returns:
            The first value read.
        """

        def value() -> T | None:
            """Read once.

            Returns:
                The read's value; None if it raised one of `ERRORS`.
            """
            try:
                return read()
            except self.ERRORS:
                return None

        found = self._each_second(value, until=lambda found: found is not None, within=self.GIVE_UP_SECONDS)
        assert found is not None, f"{self._name(read)} read nothing within {self.GIVE_UP_SECONDS} s"
        return found

    def longest_lapse_s(self, condition: Callable[[], object], *, over: float) -> float:
        """Read `condition` about once a second for `over` seconds; the longest stretch it did not hold.

        A stretch runs from the start, or a read that held, to the next read that held, or the end; each
        read counts at its end. A read that raises one of `ERRORS` does not hold.

        Args:
            condition: one read of the board; holds when truthy.
            over: how long to read for, in seconds.

        Returns:
            The longest stretch, to 0.1 s.
        """
        held_at = [time.monotonic()]

        def read() -> None:
            """Read `condition` once, keeping the read's end if it held."""
            if self._holds(condition):
                held_at.append(time.monotonic())

        self._each_second(read, until=lambda _: False, within=over)
        held_at.append(time.monotonic())
        return round(max(end - start for start, end in itertools.pairwise(held_at)), 1)

    @staticmethod
    def _each_second[T](read: Callable[[], T], *, until: Callable[[T], object], within: float) -> T:
        """Call `read` about once a second until `until` accepts what it returns, or `within` seconds pass.

        Args:
            read: one read.
            until: whether a read's value ends the reads.
            within: how long to read for, in seconds.

        Returns:
            The last read's value.
        """
        return Retrying(
            stop=stop_after_delay(within),
            wait=wait_fixed(1),
            retry=retry_if_result(lambda value: not until(value)),
            retry_error_callback=lambda state: state.outcome.result(),
        )(read)

    @staticmethod
    def _name(read: Callable) -> str:
        """Name a read for a give-up's message.

        Args:
            read: the read.

        Returns:
            Its qualified name, or its function's for a `functools.partial`.
        """
        return getattr(read, "func", read).__qualname__

    def _holds(self, condition: Callable[[], object]) -> bool:
        """Read `condition` once.

        Args:
            condition: one read of the board.

        Returns:
            Whether it was truthy; False if it raised one of `ERRORS`.
        """
        try:
            return bool(condition())
        except self.ERRORS:
            return False

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
