"""Target suite: the board rejoins after a network outage, and holds the panel under network load."""

import contextlib
import os
import subprocess
import threading
import time
from collections.abc import Callable, Iterator

import pytest
from board import Board
from outage import Outage, OutageRecord
from panel import Panel
from record import Record

_OUTAGE_SECONDS = 60
# TST029's bound
_REJOIN_BOUND_SECONDS = 30
_SHELL_TIMEOUT_SECONDS = 10
_JOURNAL_TIMEOUT_SECONDS = 60

_BLOCK_BYTES = 1024 * 1024
# TST008's period
_LOAD_SECONDS = 60
# the least average rate that counts as the load applied, in MB/s
_LOAD_FLOOR_MB_S = 1.0
# TST008's allowance for a stop, and how long the panel is watched after the load ends
_STOP_ALLOWANCE_SECONDS = 60
# how long past the load the push may run before it is killed as hung
_PUSH_GRACE_SECONDS = 60
_READ_PAUSE_SECONDS = 1


class _Push:
    """Random blocks written to an ssh for `_LOAD_SECONDS`, and how it ended.

    Attributes:
        returncode: the ssh's return code, None until it ended.
        seconds: how long the push ran, None until it ended.
        sent: the bytes written.
        received: the byte count the board's `wc -c` returned, empty if the ssh died.
    """

    returncode: int | None
    seconds: float | None
    sent: int
    received: str

    def __init__(self, proc: subprocess.Popen) -> None:
        """Bind to the ssh that takes the blocks.

        Args:
            proc: the ssh whose stdin takes the blocks and whose stdout returns the board's byte count.
        """
        self._proc = proc
        self.returncode = None
        self.seconds = None
        self.sent = 0
        self.received = ""

    def run(self) -> None:
        """Write random blocks to the ssh for `_LOAD_SECONDS`, close it, and keep how it ended."""
        started = time.monotonic()
        end = started + _LOAD_SECONDS
        try:
            while time.monotonic() < end:
                self._proc.stdin.write(os.urandom(_BLOCK_BYTES))
                self.sent += _BLOCK_BYTES
            self._proc.stdin.close()
            self.received = self._proc.stdout.read().decode(errors="replace").strip()
        except OSError:  # the ssh died or was killed
            self.received = ""
        self.returncode = self._proc.wait()
        self.seconds = time.monotonic() - started


class _PanelTally:
    """The panel's reads taken under load and after it, tallied.

    Attributes:
        reads: how many reads were attempted.
        failed: how many reads failed or carried no sample.
        off_panel: how many reads did not show the instance on the panel.
        uptimes: the board uptime of each successful read, and of the ends of the load.
        on_panel_at: the board uptime of each read that showed the instance on the panel.
        nonces: every nonce seen with the instance on the panel.
    """

    reads: int
    failed: int
    off_panel: int
    uptimes: list[float]
    on_panel_at: list[float]
    nonces: set[str]

    def __init__(self, panel: Panel, load_start: float) -> None:
        """Start the tally at the load's start.

        Args:
            panel: the probe in the browser.
            load_start: the board uptime at which the load started.
        """
        self._panel = panel
        self.reads = 0
        self.failed = 0
        self.off_panel = 0
        self.uptimes = [load_start]
        self.on_panel_at = [load_start]
        self.nonces = set()

    def read_while(self, keep_going: Callable[[], bool]) -> None:
        """Read the panel once a second while `keep_going()`, tallying each read.

        Args:
            keep_going: whether to read again.
        """
        while keep_going():
            self.reads += 1
            try:
                read = self._panel.read()
            except Board.ERRORS:
                self.failed += 1
                self.off_panel += 1
            else:
                self.uptimes.append(read.uptime)
                if read.sample is None:
                    self.failed += 1
                if self._panel.shows_instance(read.sample):
                    self.on_panel_at.append(read.uptime)
                    self.nonces.add(read.sample["nonce"])
                else:
                    self.off_panel += 1
            time.sleep(_READ_PAUSE_SECONDS)

    def longest_stop_s(self, load_end: float, observation_end: float) -> float:
        """The longest interval between on-panel reads, from the load's start to its end.

        An interval runs from an on-panel read to the next; the last runs to the end of observation.

        Args:
            load_end: the board uptime at which the load ended.
            observation_end: the board uptime at which the panel stopped being watched.

        Returns:
            The seconds, to 0.1 s.
        """
        starts = [at for at in self.on_panel_at if at <= load_end]
        ends = self.on_panel_at[1:] + [observation_end]
        return round(max(end - start for start, end in zip(starts, ends, strict=False)), 1)


class TestNetwork:
    """The board rejoins after a network outage, and holds the panel under network load."""

    @pytest.fixture(autouse=True)
    def setup(self, board: Board, record: Record) -> Iterator[None]:
        """Keep what every test here uses, and undo what each test changed once it ends.

        Args:
            board: the board under test.
            record: the test's record.

        Yields:
            None: the test runs, then `self.cleanup` undoes its changes, last first.
        """
        self.board = board
        self.record = record
        with contextlib.ExitStack() as self.cleanup:
            yield

    def _open_fresh_shell(self) -> tuple[tuple[float, list[str]] | None, str]:
        """Open a new ssh shell and read the board's uptime and the outage record over it.

        Returns:
            The uptime and the record's lines, or None if no shell opened, and how the attempt ended.
        """
        try:
            done = subprocess.run(
                [
                    *self.board.fresh_ssh_argv("ConnectTimeout=5"),
                    f"cat /proc/uptime; cat {Outage.RECORD_PATH} 2>/dev/null; true",
                ],
                capture_output=True,
                text=True,
                timeout=_SHELL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return None, f"timed out after {_SHELL_TIMEOUT_SECONDS} s"
        if done.returncode != 0:
            return None, f"rc {done.returncode}, stderr {done.stderr.strip()[-200:]!r}"
        lines = done.stdout.splitlines()
        return (float(lines[0].split()[0]), lines[1:]), "opened"

    def _journal_trace(self, boot_id: str) -> list[str]:
        """The outage unit's journal for the last run of this boot, read once the board answers again.

        Args:
            boot_id: the boot id before the outage, as `Board.BOOT_ID_CMD` prints it.

        Returns:
            The journal lines of the unit's last run, or a line naming the `journalctl` return code and
            its stderr when the read failed.
        """
        self.board.reconnect()
        journal, journal_err, journal_rc = self.board.run(
            f"journalctl -b {boot_id.replace('-', '')} -u {Outage.UNIT} -o cat --no-pager",
            timeout=_JOURNAL_TIMEOUT_SECONDS,
        )
        if journal_rc != 0:
            return [f"journalctl rc {journal_rc}", *journal_err]
        last_run = max((n for n, line in enumerate(journal) if line.startswith("id ")), default=0)
        return journal[last_run:]

    def test_rejoins_after_an_outage(self) -> None:
        """TST029 rejoins after an outage: pin the board off its network, then time until a shell opens."""
        self.record(requirement="TST029")
        outage = Outage(self.board, self.cleanup)
        outage.wait_boot_complete()
        boot_id = self.board.read(self.board.BOOT_ID_CMD)

        outage.schedule(_OUTAGE_SECONDS)
        deadline = time.monotonic() + Outage.CUT_DELAY_SECONDS + _OUTAGE_SECONDS + Outage.GIVE_UP_SECONDS
        last_attempt = "no attempt"
        shells_before_cut = 0
        shells_during_outage = 0
        rejoined_s = None
        cut_at = t0 = None
        lines = []
        while time.monotonic() < deadline:
            opened, last_attempt = self._open_fresh_shell()
            if opened is None:
                time.sleep(1)
                continue
            t1, lines = opened
            cut_at, t0, _ = OutageRecord.from_lines(lines)
            if cut_at is None or t1 < cut_at:
                shells_before_cut += 1
            elif t0 is None:
                shells_during_outage += 1
                break
            else:
                # Board uptime at both ends; overstates by up to one poll plus one connect attempt.
                rejoined_s = round(t1 - t0, 1)
                break
            time.sleep(1)

        self.record(
            outage_s=_OUTAGE_SECONDS,
            cut_uptime_s=cut_at,
            t0_uptime_s=t0,
            rejoined_s=rejoined_s,
            shells_before_cut=shells_before_cut,
            shells_during_outage=shells_during_outage,
            last_attempt=last_attempt,
            trace=[line for line in lines if line.startswith("trace ")],
        )
        if rejoined_s is None and shells_during_outage == 0:
            self.record(journal_trace=self._journal_trace(boot_id))
        assert shells_during_outage == 0, "the network did not go away: a shell opened during the outage"
        assert rejoined_s is not None, f"no remote shell within {Outage.GIVE_UP_SECONDS} s of the network returning"
        assert rejoined_s <= _REJOIN_BOUND_SECONDS, (
            f"a shell opened {rejoined_s} s after the network returned; TST029's bound is {_REJOIN_BOUND_SECONDS} s"
        )

    def test_sustained_network_load(self) -> None:
        """TST008 sustained network load: push bytes at the board; no stop of the panel may exceed 60 s."""
        self.record(requirement="TST008")
        panel = Panel(self.board, self.cleanup, self.record)
        panel.install_probe()
        panel.wait_for_instance()
        load_start = self.board.run_with_uptime(check=True)[0]
        proc = subprocess.Popen(
            [
                *self.board.fresh_ssh_argv("ConnectTimeout=10", "ServerAliveInterval=15", "ServerAliveCountMax=4"),
                "wc -c",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        self.cleanup.callback(proc.wait)
        self.cleanup.callback(proc.kill)
        push = _Push(proc)
        pusher = threading.Thread(target=push.run)
        watchdog = threading.Timer(_LOAD_SECONDS + _PUSH_GRACE_SECONDS, proc.kill)
        self.cleanup.callback(watchdog.cancel)
        tally = _PanelTally(panel, load_start)

        watchdog.start()
        pusher.start()
        tally.read_while(pusher.is_alive)
        pusher.join()
        watchdog.cancel()
        load_end = self.board.run_with_uptime(check=True)[0]
        tally.uptimes.append(load_end)
        observe_until = time.monotonic() + _STOP_ALLOWANCE_SECONDS
        tally.read_while(lambda: time.monotonic() < observe_until)

        longest_stop = tally.longest_stop_s(load_end, load_end + _STOP_ALLOWANCE_SECONDS)
        rate = push.sent / push.seconds / 1e6
        self.record(
            bytes=push.sent,
            seconds=round(push.seconds, 1),
            rate_mb_s=round(rate, 2),
            longest_stop_s=longest_stop,
            reads=tally.reads,
            off_panel_reads=tally.off_panel,
            failed_reads=tally.failed,
            nonces=sorted(tally.nonces),
        )
        assert push.returncode == 0 and push.received == str(push.sent), (
            f"the load was not applied: ssh returned {push.returncode}, sent {push.sent} B, "
            f"the board counted {push.received!r}"
        )
        assert push.seconds >= _LOAD_SECONDS and rate >= _LOAD_FLOOR_MB_S, (
            f"the load was not applied: {rate:.2f} MB/s over {push.seconds:.0f} s; "
            f"the floor is {_LOAD_FLOOR_MB_S} MB/s for {_LOAD_SECONDS} s"
        )
        assert tally.uptimes == sorted(tally.uptimes), "the board restarted during the test: its uptime went backwards"
        assert longest_stop <= _STOP_ALLOWANCE_SECONDS, (
            f"the panel was off for {longest_stop} s under load; TST008's allowance is {_STOP_ALLOWANCE_SECONDS} s"
        )
