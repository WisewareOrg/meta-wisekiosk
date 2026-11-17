"""Target suite: a page frozen without ending the browser is changing on the panel again in time."""

import re
import subprocess
import time
from pathlib import Path

_CLOCK_CONFIG = Path(__file__).resolve().parent / "clock-seconds.json"
_CAPTURE_PATH = "/tmp/tst005.png"
_DIMENSIONS = re.compile(r"dimensions:\s+(\d+)x(\d+)")

# TST005's bound
_BOUND_SECONDS = 60
# the freeze must show on the panel within this long, by board uptime
_STOPPED_WITHIN_SECONDS = 15
_CAPTURE_EVERY_SECONDS = 5
# stop capturing; past the bound, so the record still carries the time it took
_GIVE_UP_SECONDS = 120
# below this an import that returned 0 did not write a picture (kiosk-render-check.sh)
_MIN_PNG_BYTES = 100
_CHANGING_READS = 3


class _Captures:
    """The panel's middle third grabbed every `_CAPTURE_EVERY_SECONDS`, and the reads they make.

    A capture is `(board uptime just before the grab, sha256 | None)`; None is a bad capture. A
    read is two good captures in a row, and is changing when their hashes differ. `changing_run`
    counts the changing reads ending at the latest capture.
    """

    def __init__(self, board, crop):
        self._board = board
        self._crop = crop
        self._next_at = time.monotonic()
        self.captures = []
        self.changing_run = 0

    def _grab(self):
        cmd = (
            f"rm -f {_CAPTURE_PATH}; cat /proc/uptime; "
            f"DISPLAY=:0 import -window root -crop {self._crop} +repage {_CAPTURE_PATH}; "
            f"echo rc=$?; stat -c %s {_CAPTURE_PATH}; sha256sum {_CAPTURE_PATH}"
        )
        try:
            stdout, _stderr, _returncode = self._board.run(cmd)
        except subprocess.TimeoutExpired:
            return None, None
        uptime_s = float(stdout[0].split()[0])
        good = (
            len(stdout) >= 4
            and stdout[1] == "rc=0"
            and int(stdout[2]) >= _MIN_PNG_BYTES
        )
        return uptime_s, stdout[3].split()[0] if good else None

    def take(self):
        """Wait out the cadence, grab once and return the capture, updating `changing_run`."""
        time.sleep(max(0, self._next_at - time.monotonic()))
        self._next_at = time.monotonic() + _CAPTURE_EVERY_SECONDS
        capture = self._grab()
        previous = self.captures[-1] if self.captures else (None, None)
        if capture[1] is not None and previous[1] is not None and capture[1] != previous[1]:
            self.changing_run += 1
        else:
            self.changing_run = 0
        self.captures.append(capture)
        return capture

    def stopped(self):
        """The latest read is a pair of good captures with the same hash."""
        return (
            len(self.captures) >= 2
            and self.captures[-1][1] is not None
            and self.captures[-1][1] == self.captures[-2][1]
        )


def _middle_third(board):
    """The crop of the root window's middle third, where the clock sits, as `WxH+X+Y`."""
    stdout, _stderr, _returncode = board.run("DISPLAY=:0 xdpyinfo", check=True)
    match = _DIMENSIONS.search("\n".join(stdout))
    assert match is not None, "xdpyinfo reported no screen dimensions"
    width, height = int(match.group(1)), int(match.group(2))
    return f"{width}x{height // 3}+0+{height // 3}"


def test_frozen_page_recovered(board, panel, set_config, record_property, request):
    """TST005 frozen page recovered: stop the page's web processes and time until the panel changes again.

    The board shows a clock with seconds in the middle third. The panel must change three reads
    in a row before the freeze. Every `WebKitWebProcess` of the browser is then stopped with
    SIGSTOP, and the freeze is confirmed from each process's state and from the panel standing
    still within `_STOPPED_WITHIN_SECONDS`. Recovery is the first changing read that starts
    three changing reads in a row; its time is that read's second capture, by board uptime.
    """
    record_property("requirement", "TST005")
    set_config(_CLOCK_CONFIG)
    _, before = panel.wait_on_panel()

    crop = _middle_third(board)
    record_property("crop", crop)
    request.addfinalizer(lambda: board.run(f"rm -f {_CAPTURE_PATH}"))
    grabs = _Captures(board, crop)

    started = time.monotonic()
    while True:
        grabs.take()
        if grabs.changing_run >= _CHANGING_READS:
            break
        assert time.monotonic() - started <= _GIVE_UP_SECONDS, (
            "the panel was not changing before the freeze"
        )

    request.addfinalizer(lambda: board.run("pkill -CONT -P $(pgrep -x surf)"))
    stdout, _stderr, _returncode = board.run(
        'cat /proc/uptime; s=$(pgrep -x surf); p=$(pgrep -P "$s" WebKitWebProcess); '
        "echo $p; kill -STOP $p"
    )
    frozen_at = float(stdout[0].split()[0])
    frozen_pids = stdout[1].split()
    give_up_at = time.monotonic() + _GIVE_UP_SECONDS
    record_property("frozen_pids", frozen_pids)
    record_property("frozen_at_uptime_s", frozen_at)
    assert frozen_pids, "the freeze did not take: no web process of the browser was found"

    for pid in frozen_pids:
        status, _stderr, _returncode = board.run(f"grep '^State:' /proc/{pid}/status")
        assert status and status[0].split()[1] == "T", (
            f"the freeze did not take: web process {pid} is not stopped ({status!r})"
        )
    while True:
        uptime_s, _digest = grabs.take()
        if (
            grabs.stopped()
            and grabs.captures[-2][0] is not None
            and grabs.captures[-2][0] > frozen_at
        ):
            break
        assert uptime_s is None or uptime_s <= frozen_at + _STOPPED_WITHIN_SECONDS, (
            f"the freeze did not take: the panel was still changing {_STOPPED_WITHIN_SECONDS} s "
            "after it"
        )
        assert time.monotonic() < give_up_at, "the freeze did not take: no reading of the panel"

    recovered_s = None
    while time.monotonic() < give_up_at:
        grabs.take()
        if grabs.changing_run == _CHANGING_READS:
            recovered_s = round(grabs.captures[-_CHANGING_READS][0] - frozen_at, 1)
            break

    try:
        after = panel.read()[1]
    except subprocess.TimeoutExpired:
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

    assert recovered_s is not None, (
        f"the panel was not changing again within {_GIVE_UP_SECONDS} s of the freeze"
    )
    assert recovered_s <= _BOUND_SECONDS, (
        f"changing again after {recovered_s} s; TST005's bound is {_BOUND_SECONDS} s"
    )
