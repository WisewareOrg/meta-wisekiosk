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
from board.console import Console
from board.network import Network
from board.screen import Screen
from board.system import System
from board.updates import Updates


class InstanceState(NamedTuple):
    """One read of whether the instance is up: the browser running and the page served.

    Attributes:
        browser_running: `pgrep -x surf` found the browser.
        page_served: the page served an HTML document.
    """

    browser_running: bool
    page_served: bool


class BootOrder(NamedTuple):
    """The boot order and the attempts left, as `fw_printenv` holds them.

    Attributes:
        order: the slots' bootnames in the order the bootloader tries them.
        attempts_left: the attempts left per bootname.
    """

    order: list[str]
    attempts_left: dict[str, int]


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
        last_instance_state: the last read of `seconds_until_instance_up`, None before one.
        network: the board's network.
        screen: the board's screen.
        system: the board's operating system.
        updates: RAUC and the board's install path.
        BOOT_ID_CMD: prints the kernel's boot id, which differs in each boot.
        BOOT_VARIABLES_CMD: prints BOOT_ORDER and each slot's BOOT_x_LEFT as name=value lines.
        ERRORS: what a read of the board raises when the board does not answer; `poll` retries these.
        GIVE_UP_SECONDS: how long a test waits for the board; past every bound, so the record still
            carries the time it took.
        PAGE_FETCH_CMD: fetches the WiseKiosk instance's page on the board to stdout; busybox wget
            returns 0 only on 2xx.
        PAGE_ATTEMPT_TIMEOUT_SECONDS: the longest one page fetch may take.
    """

    app: App
    cleanup: contextlib.ExitStack
    console: Console
    host: str
    last_instance_state: InstanceState | None
    network: Network
    screen: Screen
    system: System
    updates: Updates
    BOOT_ID_CMD = "cat /proc/sys/kernel/random/boot_id"
    BOOT_VARIABLES_CMD = "fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT"
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
    # how long `run_reconnecting` keeps reconnecting and retrying before it gives up
    _RECONNECTING_RETRY_SECONDS = 300
    # how often `sleep_watching_boot` reads the boot, so a reboot ends the sleep early
    _BOOT_CHECK_SECONDS = 600

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
        self.console = Console(self)
        self.screen = Screen(self)
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

    def run_reconnecting(
        self, cmd: str, check: bool = False, timeout: float | None = _COMMAND_TIMEOUT_SECONDS
    ) -> tuple[list[str], list[str], int]:
        """Run `cmd` on the board, reconnecting and retrying while the session times out or drops.

        Retries for up to 300 s, then raises the last of `ERRORS` unchanged.

        Args:
            cmd: the command to run.
            check: assert the command returned 0.
            timeout: forwarded to `run`.

        Returns:
            The stdout lines, the stderr lines and the return code.
        """
        return Retrying(
            stop=stop_after_delay(self._RECONNECTING_RETRY_SECONDS),
            retry=retry_if_exception_type(self.ERRORS),
            before_sleep=lambda _state: self._reconnect_if_it_answers(),
            reraise=True,
        )(self.run, cmd, check=check, timeout=timeout)

    def uptime_s(self) -> float:
        """Read the board's uptime, retrying through a dropped session (`run_reconnecting`).

        Returns:
            The uptime, in seconds.
        """
        return float("\n".join(self.run_reconnecting("cat /proc/uptime", check=True)[0]).strip().split()[0])

    def boot_id(self) -> str:
        """Read the kernel's boot id, retrying through a dropped session (`run_reconnecting`).

        Returns:
            The boot id.
        """
        return "\n".join(self.run_reconnecting(self.BOOT_ID_CMD, check=True)[0]).strip()

    def sleep_watching_boot(self, boot_id: str, seconds: float) -> str | None:
        """Sleep out `seconds`, reading the boot every 600 s, and end early if the board booted again.

        The final read, made once more after the sleep, leaves the session live for every read after
        it.

        Args:
            boot_id: the boot the sleep starts in.
            seconds: how long to sleep.

        Returns:
            The boot id at the end, or None if it could not be read.
        """
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(min(self._BOOT_CHECK_SECONDS, max(0, end - time.monotonic())))
            now = self._boot_id_or_none()
            if now is not None and now != boot_id:
                break
        return self._boot_id_or_none()

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

    def soc_temperature_c(self) -> float | None:
        """Read the SoC's temperature.

        Returns:
            The temperature in degrees Celsius, or None if it could not be read.
        """
        stdout, _stderr, returncode = self.run("cat /sys/class/thermal/thermal_zone0/temp")
        return int(stdout[0]) / 1000 if returncode == 0 and stdout else None

    def write_log_marker(self, text: str) -> None:
        """Write `text` to the board's journal under the identifier `kiosk-log-marker`.

        Args:
            text: the marker line.
        """
        self.run(f"echo {text} | systemd-cat -t kiosk-log-marker", check=True)

    def log_markers(self) -> list[str] | None:
        """Read the marker lines written to the journal under the identifier `kiosk-log-marker`.

        Returns:
            The lines, or None if `journalctl` returned nonzero.
        """
        stdout, _stderr, returncode = self.run("journalctl -t kiosk-log-marker -o cat")
        return stdout if returncode == 0 else None

    def builtin_modules(self) -> list[str]:
        """Read the kernel modules built into the running kernel.

        Returns:
            The lines of its `modules.builtin`.
        """
        return self.run("cat /lib/modules/$(uname -r)/modules.builtin", check=True)[0]

    def boot_order(self) -> BootOrder:
        """Read BOOT_ORDER and each slot's BOOT_x_LEFT from `fw_printenv`.

        Returns:
            The boot order, and the attempts left per bootname.
        """
        stdout = self.run(self.BOOT_VARIABLES_CMD, check=True)[0]
        variables = dict(line.split("=", 1) for line in stdout)
        attempts_left = {name: int(variables[f"BOOT_{name}_LEFT"]) for name in ("A", "B")}
        return BootOrder(variables["BOOT_ORDER"].split(), attempts_left)

    def build_commit(self) -> str:
        """Read the meta-wisekiosk commit the board's image was built from.

        Returns:
            The commit named by the meta-wisekiosk line of /etc/buildinfo.
        """
        stdout, _stderr, returncode = self.run("cat /etc/buildinfo", timeout=None)
        assert returncode == 0, "could not read /etc/buildinfo on the board"
        line = next((entry for entry in stdout if entry.split()[:2] == ["meta-wisekiosk", "="]), None)
        assert line is not None, f"no meta-wisekiosk layer line in buildinfo:\n{chr(10).join(stdout)}"
        return line.split()[2].rsplit(":", 1)[-1]

    def file_sha256(self, path: str) -> str | None:
        """Read the sha256 of the file `path` on the board.

        Args:
            path: the file on the board.

        Returns:
            The hash, or None if `sha256sum` returns nonzero (the file is missing or unreadable).
        """
        stdout, _stderr, returncode = self.run(f"sha256sum {path}")
        if returncode != 0:
            return None
        return stdout[0].split()[0]

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

    def install_built_image(self) -> None:
        """Install the image this checkout built on the board, through `just kiosk-ota`."""
        subprocess.run(["just", "kiosk-ota", self.host], check=True)

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

    def _reconnect_if_it_answers(self) -> None:
        """Reconnect the SSHDriver, and carry on if the board does not answer in time."""
        with contextlib.suppress(AssertionError):
            self.reconnect()

    def _boot_id_or_none(self) -> str | None:
        """Read the kernel's boot id through `boot_id`.

        Returns:
            The boot id, or None if it could not be read.
        """
        try:
            return self.boot_id()
        except self.ERRORS:
            return None

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
