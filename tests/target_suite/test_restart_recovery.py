"""Target suite: a board that went down, nobody at the panel, brings the instance back in time.

It restarted, crashed, lost power or started its backend late.
"""

import time

from panel import Panel, loaded_instance
from recovery import (
    GIVE_UP_SECONDS,
    assert_back_within,
    assert_on_panel_within,
    check_held,
    or_none,
    panel_after_answer,
    poll_from,
    until_up,
)

# TST004's bound
_CRASH_BOUND_SECONDS = 100
# TST011's bound
_RESTART_BOUND_SECONDS = 60
# TST002's bound
_POWER_CUT_BOUND_SECONDS = 60
# TST012's bound
_COLD_BOOT_BOUND_SECONDS = 110
# TST033's bound
_LATE_BACKEND_BOUND_SECONDS = 60

_USERSPACE_BOOT_CMD = "systemctl show -p ActiveEnterTimestampMonotonic --value multi-user.target"
_RELEASE = "systemctl unmask --runtime wisekiosk.service; systemctl start wisekiosk.service"
_RELEASE_UNIT = "test-backend-release"


def _back_s(board, cmd):
    """Run `cmd`; return seconds until the instance is up (None if never) and the last read."""
    board.wait_for_page()
    started = time.monotonic()
    board.restart_by(cmd)
    # Overstates by the boot-id read, the disconnect and the ssh connect before the fault lands.
    return until_up(board, started)


def _release(board):
    """Unmask and start the backend, then wait for the page; idempotent."""
    board.run(_RELEASE, check=True)
    board.wait_for_page()


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
    """TST002 power cut while showing: cut power with the instance up.

    Times from power returning until the page is served with the browser running.
    """
    record_property("requirement", "TST002")
    ready_s, last_read = until_up(board, time.monotonic())
    assert ready_s is not None, f"the instance was not up before the cut; last read: {last_read}"
    started = power_cut()
    back_s, last_read = until_up(board, started)
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    assert_back_within(back_s, last_read, "power returning", "TST002", _POWER_CUT_BOUND_SECONDS)


def test_cold_boot_to_the_panel(board, power_cut, record_property):
    """TST012 cold boot to the panel: cut power.

    Times from power returning until the browser has finished loading the instance's page.
    """
    record_property("requirement", "TST012")
    panel = Panel(board)
    started = power_cut()
    on_panel_s, titles = poll_from(started, lambda: or_none(panel.titles), lambda t: loaded_instance(t) is not None)
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


def test_backend_late_at_boot(board, request, record_property):
    """TST033 backend late at boot: time from the held backend's first answer to the instance on the panel.

    The backend is masked across a soft-reboot and released three ways, each idempotent: by the
    test once the browser has finished a load without it, by a board-side timer armed on
    reconnect, and at teardown before the probe's own teardown restarts the browser.
    """
    record_property("requirement", "TST033")
    panel = Panel(board)
    board.wait_for_page()

    request.addfinalizer(lambda: _release(board))
    board.run("systemctl mask --runtime wisekiosk.service", check=True)
    board.restart_by("systemctl soft-reboot", boot_cmd=_USERSPACE_BOOT_CMD)

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

    check_held(board, panel, record_property)

    board.run(_RELEASE, check=True)
    t0, on_panel_s, last = panel_after_answer(board, panel)
    record_property("backend_answered_uptime_s", t0)
    record_property("on_panel_s", on_panel_s)
    record_property("last_sample", last[1] if last else None)
    record_property("last_titles", or_none(panel.titles))
    assert_on_panel_within(t0, on_panel_s, last, "TST033", _LATE_BACKEND_BOUND_SECONDS)
