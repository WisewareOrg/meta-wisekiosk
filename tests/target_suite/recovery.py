"""Whether a board that went down serves the instance again: the page served with the browser running."""

import subprocess
import time

from labgrid.driver.exception import ExecutionError

from panel import loaded_other_page

# stop polling; past every bound, so the record still carries the time it took
GIVE_UP_SECONDS = 180


def instance_up(board):
    """Read whether the browser is running and whether the page is served, as a pair."""
    try:
        _, _, browser = board.run("pgrep -x surf")
    except (ExecutionError, subprocess.TimeoutExpired):
        browser = None
    try:
        page_served = board.page_served()
    except ExecutionError:
        page_served = False
    return browser == 0, page_served


def poll_from(started, read, done):
    """Poll `read` once a second from `started` until `done(value)`; return seconds and the last value.

    Seconds is None when `GIVE_UP_SECONDS` passed first, and overstates by at most one read plus the
    1 s sleep. A read returning None is a failed read: it does not replace the last value.
    """
    last = None
    while True:
        value = read()
        if value is not None:
            last = value
            if done(value):
                return round(time.monotonic() - started, 1), last
        if time.monotonic() - started > GIVE_UP_SECONDS:
            return None, last
        time.sleep(1)


def until_up(board, started):
    """Poll from `started` until the instance is up; return seconds (None if never) and the last read."""
    return poll_from(started, lambda: instance_up(board), all)


def assert_back_within(back_s, last_read, fault, requirement, bound):
    """Assert the instance was back, and within the bound."""
    assert back_s is not None, (
        f"the board did not serve the page with the browser running within {GIVE_UP_SECONDS} s "
        f"of the {fault}; last read: browser running {last_read[0]}, page served {last_read[1]}"
    )
    assert back_s <= bound, (
        f"back after {back_s} s; {requirement}'s bound is {bound} s"
    )


def or_none(read):
    """`read()`, or None when the board read failed."""
    try:
        return read()
    except (ExecutionError, subprocess.TimeoutExpired):
        return None


def held_state(board, panel):
    """Whether the browser runs, whether the page is served, and what it shows that is not the instance.

    The last is `("probe", sample)` for a probe sample neither on the panel nor still loading,
    `("title", title)` for a finished title that is not the instance's when there is no sample,
    else None.
    """
    running = board.run("pgrep -x surf")[2] == 0
    served = board.page_served()
    _, sample = panel.read()
    if sample is not None:
        settled_off_panel = not panel.on_panel(sample) and sample["state"] != "loading"
        shown = ("probe", sample) if settled_off_panel else None
    else:
        title = loaded_other_page(panel.titles())
        shown = ("title", title) if title else None
    return running, served, shown


def wait_held(board, panel):
    """Poll until the browser shows a page that is not the instance without the page served, or until
    the page is served; return seconds (None if neither) and the last `held_state`."""
    return poll_from(
        time.monotonic(),
        lambda: or_none(lambda: held_state(board, panel)),
        lambda state: state[1] or (state[0] and state[2] is not None),
    )


def assert_held(held_s, held):
    """Assert `wait_held` saw the browser hold a page that is not the instance without the backend."""
    assert held_s is not None, (
        f"INVALID CHECK, not an appliance failure: the browser had not finished a load without the "
        f"backend within {GIVE_UP_SECONDS} s; last (browser running, page served, shown): {held!r}"
    )
    assert not held[1], (
        "INVALID CHECK, not an appliance failure: the page was served before the browser had "
        f"finished a load without the backend, so the hold was too short; last: {held!r}"
    )


def uptime_and_served(board):
    """The board uptime and whether the page served, from one command."""
    stdout, _stderr, returncode = board.run(
        f"cat /proc/uptime; wget -q -O- {board.PAGE_URL}", timeout=board.PAGE_ATTEMPT_TIMEOUT_SECONDS
    )
    return float(stdout[0].split()[0]), returncode == 0 and "<html" in "\n".join(stdout[1:])


def panel_after_answer(board, panel):
    """Poll until the page is first served, then until the instance is on the panel.

    The first serve is polled once a second, so it is read up to one poll late.

    Returns:
        tuple: the board uptime of the first serve (None if never), seconds from it to the
            instance on the panel (None if never), and the last panel read as (uptime, sample).
    """
    answered_s, answered = poll_from(
        time.monotonic(), lambda: or_none(lambda: uptime_and_served(board)), lambda read: read[1]
    )
    if answered_s is None:
        return None, None, None
    t0 = answered[0]
    _, last = poll_from(time.monotonic(), lambda: or_none(panel.read), lambda read: panel.on_panel(read[1]))
    on_panel_s = round(last[0] - t0, 1) if last and panel.on_panel(last[1]) else None
    return t0, on_panel_s, last


def assert_on_panel_within(t0, on_panel_s, last, requirement, bound):
    """Assert the backend answered and the instance was then on the panel within `bound`."""
    assert t0 is not None, f"the backend did not answer within {GIVE_UP_SECONDS} s"
    assert on_panel_s is not None, (
        f"the instance was not on the panel within {GIVE_UP_SECONDS} s of the backend answering; "
        f"last panel read: {last!r}"
    )
    assert on_panel_s <= bound, (
        f"on the panel {on_panel_s} s after the backend answered; {requirement}'s bound is {bound} s"
    )


_HOLD_DIR = "/run/systemd/system/wisekiosk.service.d"
_HOLD_PATH = f"{_HOLD_DIR}/hold.conf"
_MAIN_PID_CMD = "systemctl show -p MainPID --value wisekiosk.service"


def hold_restart(board, request, seconds):
    """Delay the backend's own restart to `seconds` with a runtime drop-in; undo it at teardown.

    Returns:
        Callable[[], None]: the undo -- remove the drop-in, start the backend and wait for the
            page; idempotent, so a caller may register it again to run earlier at teardown.
    """

    def unhold():
        board.run(
            f"rm -f {_HOLD_PATH}; systemctl daemon-reload; systemctl start wisekiosk.service", check=True
        )
        assert board.wait_for_page(), "the page did not serve after the restart hold was removed"

    request.addfinalizer(unhold)
    board.run(
        f"mkdir -p {_HOLD_DIR} && printf '[Service]\\nRestartSec={seconds}\\n' > {_HOLD_PATH} && "
        "systemctl daemon-reload",
        check=True,
    )
    return unhold


def main_pid(board):
    """The backend's MainPID as systemd reports it."""
    return board.run(_MAIN_PID_CMD, check=True)[0][0].strip()


def kill_backend(board):
    """SIGKILL the backend; return the board uptime of the kill and the MainPID before it."""
    old_pid = main_pid(board)
    stdout, _stderr, _returncode = board.run(
        "cat /proc/uptime; systemctl kill --signal=KILL wisekiosk.service", check=True
    )
    return float(stdout[0].split()[0]), old_pid


def assert_kill_landed(board, old_pid):
    """Assert the backend answering after the kill is a new process; return its MainPID."""
    new_pid = main_pid(board)
    assert new_pid != old_pid, (
        f"INVALID CHECK, not an appliance failure: the kill did not land (MainPID {old_pid} unchanged)"
    )
    return new_pid
