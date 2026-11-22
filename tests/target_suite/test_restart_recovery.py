"""Target suite: a board that went down, nobody at the panel, brings the instance back in time.

It restarted, crashed, lost power or started its backend late.
"""

import time

import pytest
from backend import Backend
from board import Board, PowerCut
from panel import Panel
from record import Record

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


def _back_s(board: Board, cmd: str) -> tuple[float | None, tuple[bool, bool] | None]:
    """Run `cmd` on the board and time until the instance is up.

    Overstates by the boot-id read, the disconnect and the ssh connect before the fault lands.

    Args:
        board: the board under test.
        cmd: the command that restarts or crashes the board.

    Returns:
        The seconds until the page is served with the browser running (None if never), and the last
        read as (browser running, page served).
    """
    board.wait_for_page()
    started = time.monotonic()
    board.restart_by(cmd)
    return board.until_up(started)


def _loaded(titles: list[str]) -> str | None:
    """The title of a window surf has finished loading the instance's page into.

    surf titles a window `<indicators>:<indicators> | <page title>`, prefixed `[NN%] ` while the page
    loads; the instance's page title is `WiseKiosk`.

    Args:
        titles: every window's title.

    Returns:
        The title, or None if there is none.
    """
    return next((t for t in titles if t.endswith(" | WiseKiosk") and not t.startswith("[")), None)


def test_kernel_crash(board: Board, record: Record) -> None:
    """TST004 kernel crash: crash the kernel and time until the page is served, browser running.

    Args:
        board: the board under test, crashed here.
        record: records the requirement, the time back and the last read.
    """
    record(requirement="TST004")
    back_s, last_read = _back_s(board, "echo c > /proc/sysrq-trigger")
    record(back_s=back_s, last_read=last_read)
    assert back_s is not None and back_s <= _CRASH_BOUND_SECONDS, (
        f"back after {back_s} s (None: not within {Board.GIVE_UP_SECONDS} s of the crash); "
        f"bound {_CRASH_BOUND_SECONDS} s; last read {last_read}"
    )


def test_restart_to_the_panel(board: Board, record: Record) -> None:
    """TST011 restart to the panel: restart the board; time until the page is served, browser up.

    Args:
        board: the board under test, restarted here.
        record: records the requirement, the time back and the last read.
    """
    record(requirement="TST011")
    back_s, last_read = _back_s(board, "systemctl reboot")
    record(back_s=back_s, last_read=last_read)
    assert back_s is not None and back_s <= _RESTART_BOUND_SECONDS, (
        f"back after {back_s} s (None: not within {Board.GIVE_UP_SECONDS} s of the restart); "
        f"bound {_RESTART_BOUND_SECONDS} s; last read {last_read}"
    )


def test_power_cut_while_showing(board: Board, power_cut: PowerCut, record: Record) -> None:
    """TST002 power cut while showing: cut power with the instance up.

    Times from power returning until the page is served with the browser running.

    Args:
        board: the board under test, whose power is cut.
        power_cut: cuts the power and returns the instant it came back.
        record: records the requirement, the time back and the last read.
    """
    record(requirement="TST002")
    ready_s, last_read = board.until_up(time.monotonic())
    assert ready_s is not None, f"the instance was not up before the cut; last read: {last_read}"
    started = power_cut()
    back_s, last_read = board.until_up(started)
    record(back_s=back_s, last_read=last_read)
    assert back_s is not None and back_s <= _POWER_CUT_BOUND_SECONDS, (
        f"back after {back_s} s (None: not within {Board.GIVE_UP_SECONDS} s of power returning); "
        f"bound {_POWER_CUT_BOUND_SECONDS} s; last read {last_read}"
    )


def test_cold_boot_to_the_panel(
    board: Board,
    power_cut: PowerCut,
    request: pytest.FixtureRequest,
    record: Record,
) -> None:
    """TST012 cold boot to the panel: cut power.

    Times from power returning until the browser has finished loading the instance's page.

    Args:
        board: the board under test, whose power is cut.
        power_cut: cuts the power and returns the instant it came back.
        request: the test's request, which the panel registers its undos on.
        record: records the requirement, the time, the last titles and the loaded title.
    """
    record(requirement="TST012")
    panel = Panel(board, request, record)
    started = power_cut()
    on_panel_s, _ = panel.until(lambda read: _loaded(read[2]) is not None, Board.GIVE_UP_SECONDS, since=started)
    titles = panel.last_reading[2] if panel.last_reading else None
    record(on_panel_s=on_panel_s, last_titles=titles, loaded=_loaded(titles) if titles else None)
    assert on_panel_s is not None, (
        f"the browser had not finished loading the instance within {Board.GIVE_UP_SECONDS} s "
        f"of power returning; last window titles: {titles!r}"
    )
    assert on_panel_s <= _COLD_BOOT_BOUND_SECONDS, (
        f"the browser finished loading after {on_panel_s} s; bound {_COLD_BOOT_BOUND_SECONDS} s"
    )


def test_backend_late_at_boot(
    board: Board,
    backend: Backend,
    request: pytest.FixtureRequest,
    record: Record,
) -> None:
    """TST033 backend late at boot: time from the held backend's first answer to the instance on the panel.

    The backend is masked across a soft-reboot and released three ways, each idempotent: by the
    test once the browser has finished a load without it, by a board-side timer armed on
    reconnect, and at teardown before the probe's own teardown restarts the browser.

    Args:
        board: the board under test, soft-rebooted here.
        backend: masks and releases the backend.
        request: the test's request, on which the probe's unmask is registered again so it runs
            before the probe's teardown.
        record: records the requirement and what the backend and the panel measure.
    """
    record(requirement="TST033")
    panel = Panel(board, request, record)
    board.wait_for_page()

    backend.mask()
    board.restart_by("systemctl soft-reboot", boot_cmd=_USERSPACE_BOOT_CMD)
    backend.release_after(Board.GIVE_UP_SECONDS)

    enabled = board.run("systemctl is-enabled wisekiosk.service")[0]
    active = board.run("systemctl is-active wisekiosk.service")[0]
    record(backend_enabled_after_restart=enabled, backend_active_after_restart=active)
    assert enabled == ["masked-runtime"] and active != ["active"], (
        "INVALID CHECK, not an appliance failure: the hold did not survive the soft-reboot "
        f"(is-enabled {enabled}, is-active {active})"
    )

    panel.install(restart_browser=False)
    request.addfinalizer(backend.unmask)

    panel.held()

    backend.release()
    panel.after_answer()
    panel.assert_on_panel_within(_LATE_BACKEND_BOUND_SECONDS)
