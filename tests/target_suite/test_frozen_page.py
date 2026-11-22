"""Target suite: a page frozen without ending the browser is changing on the panel again in time."""

import re
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from backend import Backend
from board import Board
from panel import Panel

_CLOCK_CONFIG = Path(__file__).resolve().parent / "clock-seconds.json"
_CAPTURE_PATH = "/tmp/tst005.png"
_DIMENSIONS = re.compile(r"dimensions:\s+(\d+)x(\d+)")

# TST005's bound
_BOUND_SECONDS = 60
# the freeze must show on the panel within this long, by board uptime
_STOPPED_WITHIN_SECONDS = 15
_CAPTURE_EVERY_SECONDS = 5
# how long the test keeps capturing
_GIVE_UP_SECONDS = 120
# below this an import that returned 0 did not write a picture (kiosk-render-check.sh)
_MIN_PNG_BYTES = 100
_CHANGING_READS = 3


class _Captures:
    """The panel's middle third grabbed every `_CAPTURE_EVERY_SECONDS`, and the reads they make.

    A capture is `(board uptime just before the grab, sha256 | None)`; None is a bad capture. A
    read is two good captures in a row, and is changing when their hashes differ. `changing_run`
    counts the changing reads ending at the latest capture.

    Attributes:
        crop: the root window's middle third, where the clock sits, as `WxH+X+Y`.
        captures: every capture taken, in order.
        changing_run: the changing reads ending at the latest capture.
    """

    crop: str
    captures: list[tuple[float | None, str | None]]
    changing_run: int

    def __init__(self, board: Board) -> None:
        """Read the crop from the root window's size and start the cadence clock.

        Args:
            board: the board under test.
        """
        self._board = board
        match = _DIMENSIONS.search(board.read("DISPLAY=:0 xdpyinfo"))
        assert match is not None, "xdpyinfo reported no screen dimensions"
        width, height = int(match.group(1)), int(match.group(2))
        self.crop = f"{width}x{height // 3}+0+{height // 3}"
        self._next_at = time.monotonic()
        self.captures = []
        self.changing_run = 0

    def take(self) -> tuple[float | None, str | None]:
        """Wait out the cadence, grab once and return the capture, updating `changing_run`.

        Returns:
            The board uptime just before the grab and the sha256 of the picture; both None if the
            board did not answer, the hash alone None if no picture was written.
        """
        time.sleep(max(0, self._next_at - time.monotonic()))
        self._next_at = time.monotonic() + _CAPTURE_EVERY_SECONDS
        cmd = (
            f"rm -f {_CAPTURE_PATH}; DISPLAY=:0 import -window root -crop {self.crop} +repage {_CAPTURE_PATH}; "
            f"echo rc=$?; stat -c %s {_CAPTURE_PATH}; sha256sum {_CAPTURE_PATH}"
        )
        try:
            uptime, stdout, _stderr, _returncode = self._board.run_with_uptime(cmd)
        except Board.ERRORS:
            capture = (None, None)
        else:
            good = len(stdout) >= 3 and stdout[0] == "rc=0" and int(stdout[1]) >= _MIN_PNG_BYTES
            capture = (uptime, stdout[2].split()[0] if good else None)
        previous = self.captures[-1] if self.captures else (None, None)
        if capture[1] is not None and previous[1] is not None and capture[1] != previous[1]:
            self.changing_run += 1
        else:
            self.changing_run = 0
        self.captures.append(capture)
        return capture

    def stopped(self) -> bool:
        """Whether the latest read is a pair of good captures with the same hash.

        Returns:
            True if the last two captures are good and equal.
        """
        return (
            len(self.captures) >= 2
            and self.captures[-1][1] is not None
            and self.captures[-1][1] == self.captures[-2][1]
        )


def test_frozen_page_recovered(
    board: Board,
    backend: Backend,
    panel: Panel,
    record_property: Callable[[str, object], None],
    request: pytest.FixtureRequest,
) -> None:
    """TST005 frozen page recovered: stop the page's web processes and time until the panel changes again.

    The board shows a clock with seconds in the middle third. The panel must change three reads
    in a row before the freeze. Every `WebKitWebProcess` of the browser is then stopped with
    SIGSTOP, and the freeze is confirmed from each process's state and from the panel standing
    still within `_STOPPED_WITHIN_SECONDS`. Recovery is the first changing read that starts
    three changing reads in a row; its time is that read's second capture, by board uptime.

    Args:
        board: the board under test, whose panel is captured and whose browser's web processes are
            stopped.
        backend: swaps the board onto the clock config.
        panel: the probe in the browser, read for the instance on the panel before the freeze.
        record_property: records the requirement and what the captures and the freeze measure.
        request: the test's request, which removes the capture and continues the frozen processes
            at teardown.
    """
    record_property("requirement", "TST005")
    backend.use_config(_CLOCK_CONFIG)
    _, before = panel.wait_for_instance()

    request.addfinalizer(lambda: board.run(f"rm -f {_CAPTURE_PATH}"))
    grabs = _Captures(board)
    record_property("crop", grabs.crop)

    changing_s, _ = board.poll(
        grabs.take, until=lambda _capture: grabs.changing_run >= _CHANGING_READS, within=_GIVE_UP_SECONDS, every=0
    )
    assert changing_s is not None, "the panel was not changing before the freeze"

    frozen_pids: list[str] = []
    request.addfinalizer(lambda: frozen_pids and board.run(f"kill -CONT {' '.join(frozen_pids)}"))
    frozen_at, stdout, _stderr, _returncode = board.run_with_uptime(
        's=$(pgrep -x surf); p=$(pgrep -P "$s" WebKitWebProcess); echo $p; kill -STOP $p'
    )
    frozen = time.monotonic()
    frozen_pids[:] = stdout[0].split()
    record_property("frozen_pids", frozen_pids)
    record_property("frozen_at_uptime_s", frozen_at)
    assert frozen_pids, "the freeze did not take: no web process of the browser was found"

    for pid in frozen_pids:
        status, _stderr, _returncode = board.run(f"grep '^State:' /proc/{pid}/status")
        assert status and status[0].split()[1] == "T", (
            f"the freeze did not take: web process {pid} is not stopped ({status!r})"
        )

    def in_time(capture: tuple[float | None, str | None]) -> bool:
        """Whether a capture was taken within `_STOPPED_WITHIN_SECONDS` of the freeze, by board uptime.

        Args:
            capture: the capture to judge.

        Returns:
            True if it carries an uptime and the uptime is within the window.
        """
        return capture[0] is not None and capture[0] <= frozen_at + _STOPPED_WITHIN_SECONDS

    def seen_stopped(capture: tuple[float | None, str | None]) -> bool:
        """Whether the panel stood still within the window, or a read came after it.

        Args:
            capture: the capture just taken.

        Returns:
            True if the latest read stood still after the freeze, or the capture is past the window.
        """
        past_window = capture[0] is not None and not in_time(capture)
        return past_window or (in_time(capture) and grabs.stopped() and grabs.captures[-2][0] > frozen_at)

    stopped_s, last = board.poll(grabs.take, until=seen_stopped, within=_GIVE_UP_SECONDS, every=0, since=frozen)
    assert stopped_s is not None, "the freeze did not take: no reading of the panel"
    assert in_time(last), (
        f"the freeze did not take: the panel was not seen stopped within {_STOPPED_WITHIN_SECONDS} s of it"
    )

    changing_again_s, _ = board.poll(
        grabs.take,
        until=lambda _capture: grabs.changing_run == _CHANGING_READS,
        within=_GIVE_UP_SECONDS,
        every=0,
        since=frozen,
    )
    recovered_s = round(grabs.captures[-_CHANGING_READS][0] - frozen_at, 1) if changing_again_s is not None else None

    try:
        after = panel.read()[1]
    except Board.ERRORS:
        after = None
    log, _stderr, _returncode = board.run(
        "journalctl -b -u kiosk.service -o short-monotonic --no-pager | grep -F 'surf: page'",
        timeout=None,
    )
    record_property("before", before)
    record_property("after", after)
    record_property("recovery_log", "\n".join(log))
    record_property("captures", grabs.captures)
    record_property("recovered_s", recovered_s)

    assert recovered_s is not None, f"the panel was not changing again within {_GIVE_UP_SECONDS} s of the freeze"
    assert recovered_s <= _BOUND_SECONDS, f"changing again after {recovered_s} s; bound {_BOUND_SECONDS} s"
