"""Target suite: a restarted, crashed or power-cut board, nobody at the panel, serves the instance in time."""

import subprocess
import time

from labgrid.driver.exception import ExecutionError

from panel import Panel, loaded_instance, loaded_other_page
from recovery import GIVE_UP_SECONDS, assert_back_within, poll_from, until_up

# TST004's bound
_CRASH_BOUND_SECONDS = 100
# TST011's bound
_RESTART_BOUND_SECONDS = 60
# TST002's bound
_POWER_CUT_BOUND_SECONDS = 60
# TST012's bound
_COLD_BOOT_BOUND_SECONDS = 110


def _back_s(board, cmd):
    """Run `cmd`; return seconds until the instance is up (None if never) and the last read."""
    assert board.wait_for_page(), "the board did not serve the page before the fault"
    started = time.monotonic()
    board.restart_by(cmd)
    # Overstates by the boot-id read, the disconnect and the ssh connect before the fault lands.
    return until_up(board, started)


def test_kernel_crash(board, record_property):
    """TST004 kernel crash: crash the kernel and time until the page is served, browser running."""
    record_property("requirement", "TST004")
    back_s, last_read = _back_s(board, "echo c > /proc/sysrq-trigger")
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    assert_back_within(back_s, last_read, "crash", "TST004", _CRASH_BOUND_SECONDS)


def test_restart_to_the_panel(board, record_property):
    """TST011 restart to the panel: restart the board; time until the page is served, browser up."""
    record_property("requirement", "TST011")
    back_s, last_read = _back_s(board, "systemctl reboot")
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    assert_back_within(back_s, last_read, "restart", "TST011", _RESTART_BOUND_SECONDS)


def test_power_cut_while_showing(board, power_cut, record_property):
    """Cut power with the instance up; time until the page is served with the browser running."""
    record_property("requirement", "TST002")
    ready_s, last_read = until_up(board, time.monotonic())
    assert ready_s is not None, f"the instance was not up before the cut; last read: {last_read}"
    started = power_cut()
    back_s, last_read = until_up(board, started)
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    assert_back_within(back_s, last_read, "power returning", "TST002", _POWER_CUT_BOUND_SECONDS)


def test_cold_boot_to_the_panel(board, power_cut, record_property):
    """Cut power; time until the browser has finished loading the instance's page."""
    record_property("requirement", "TST012")
    panel = Panel(board)
    started = power_cut()
    on_panel_s, titles = poll_from(
        started, panel.titles_or_none, lambda t: loaded_instance(t) is not None
    )
    record_property("on_panel_s", on_panel_s)
    record_property("last_titles", titles)
    record_property("loaded", loaded_instance(titles) if titles else None)
    assert on_panel_s is not None, (
        f"the browser had not finished loading the instance within {GIVE_UP_SECONDS} s "
        f"of power returning; last window titles: {titles!r}"
    )
    assert on_panel_s <= _COLD_BOOT_BOUND_SECONDS, (
        f"the browser finished loading after {on_panel_s} s; TST012's bound is {_COLD_BOOT_BOUND_SECONDS} s"
    )


# TST033's bound
_LATE_BACKEND_BOUND_SECONDS = 60
_USERSPACE_BOOT_CMD = "systemctl show -p ActiveEnterTimestampMonotonic --value multi-user.target"
_RELEASE = "systemctl unmask --runtime wisekiosk.service; systemctl start wisekiosk.service"
_RELEASE_UNIT = "test-backend-release"


def _release(board):
    """Unmask and start the backend, then wait for the page; idempotent."""
    board.run(_RELEASE, check=True)
    assert board.wait_for_page(), "the page did not serve after the backend was released"


def _or_none(read):
    """`read()`, or None when the board read failed."""
    try:
        return read()
    except (ExecutionError, subprocess.TimeoutExpired):
        return None


def _held_state(board, panel):
    """Whether the browser runs, whether the page is served, and a finished load that is not the instance."""
    return board.run("pgrep -x surf")[2] == 0, board.page_served(), loaded_other_page(panel.titles())


def _uptime_and_served(board):
    """The board uptime and whether the page served, from one command."""
    stdout, _stderr, returncode = board.run(
        f"cat /proc/uptime; wget -q -O- {board.PAGE_URL}", timeout=board.PAGE_ATTEMPT_TIMEOUT_SECONDS
    )
    return float(stdout[0].split()[0]), returncode == 0 and "<html" in "\n".join(stdout[1:])


def test_backend_late_at_boot(board, request, record_property):
    """TST033 backend late at boot: time from the held backend's first answer to the instance on the panel.

    The backend is masked across a soft-reboot and released three ways, each idempotent: by the
    test once the browser has finished a load without it, by a board-side timer armed on
    reconnect, and at teardown before the probe's own teardown restarts the browser.
    """
    record_property("requirement", "TST033")
    panel = Panel(board)
    assert board.wait_for_page(), "the board did not serve the page before the restart"

    request.addfinalizer(lambda: _release(board))
    board.run("systemctl mask --runtime wisekiosk.service", check=True)
    try:
        board.restart_by("systemctl soft-reboot", boot_cmd=_USERSPACE_BOOT_CMD)
    except AssertionError as error:
        raise AssertionError(
            f"INVALID CHECK, not an appliance failure: the soft-reboot did not complete: {error}"
        ) from error

    units = f"{_RELEASE_UNIT}.timer {_RELEASE_UNIT}.service"
    request.addfinalizer(lambda: board.run(f"systemctl stop {units}; systemctl reset-failed {units}"))
    board.run(
        f"systemd-run --unit={_RELEASE_UNIT} --on-active={GIVE_UP_SECONDS} /bin/sh -c '{_RELEASE}'",
        check=True,
    )

    enabled = board.run("systemctl is-enabled wisekiosk.service")[0]
    active = board.run("systemctl is-active wisekiosk.service")[0]
    record_property("backend_enabled_after_restart", enabled)
    record_property("backend_active_after_restart", active)
    assert enabled == ["masked-runtime"] and active != ["active"], (
        "INVALID CHECK, not an appliance failure: the hold did not survive the soft-reboot "
        f"(is-enabled {enabled}, is-active {active})"
    )

    record_property("probe_sha256", panel.install(request, restart_browser=False))
    request.addfinalizer(lambda: _release(board))

    held_s, held = poll_from(
        time.monotonic(),
        lambda: _or_none(lambda: _held_state(board, panel)),
        lambda state: state[0] and not state[1] and state[2] is not None,
    )
    record_property("held_state", held)
    assert held_s is not None, (
        f"INVALID CHECK, not an appliance failure: the browser had not finished a load without the "
        f"backend within {GIVE_UP_SECONDS} s; last (browser running, page served, title): {held!r}"
    )

    board.run(_RELEASE, check=True)
    # Polled once a second, so the first answer is read up to one poll late.
    answered_s, answered = poll_from(
        time.monotonic(), lambda: _or_none(lambda: _uptime_and_served(board)), lambda read: read[1]
    )
    assert answered_s is not None, f"the backend did not answer within {GIVE_UP_SECONDS} s of its release"
    answered_at = answered[0]
    record_property("backend_answered_uptime_s", answered_at)

    _, last = poll_from(time.monotonic(), lambda: _or_none(panel.read), lambda read: panel.on_panel(read[1]))
    on_panel_s = round(last[0] - answered_at, 1) if last and panel.on_panel(last[1]) else None
    record_property("on_panel_s", on_panel_s)
    record_property("last_sample", last[1] if last else None)
    record_property("last_titles", panel.titles_or_none())
    assert on_panel_s is not None, (
        f"the instance was not on the panel within {GIVE_UP_SECONDS} s of the backend answering; "
        f"last sample: {last!r}"
    )
    assert on_panel_s <= _LATE_BACKEND_BOUND_SECONDS, (
        f"on the panel {on_panel_s} s after the backend answered; "
        f"TST033's bound is {_LATE_BACKEND_BOUND_SECONDS} s"
    )
