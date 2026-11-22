"""Target suite: the browser killed with nobody at the panel is back on the panel in time."""

from collections.abc import Callable

from board import Board
from panel import Panel

# TST001's bound
_BOUND_SECONDS = 45
# stop polling; past the bound, so the record still carries the time it took
_GIVE_UP_SECONDS = 120


def test_browser_killed(board: Board, panel: Panel, record_property: Callable[[str, object], None]) -> None:
    """TST001 browser killed: SIGKILL the browser and time until the instance is on the panel again.

    Args:
        board: the board under test, whose browser is killed.
        panel: the probe in the browser, read for the instance back on the panel with a new nonce.
        record_property: records the requirement, the samples around the kill and the time back.
    """
    record_property("requirement", "TST001")
    _, before = panel.wait_on_panel()

    killed_at = board.run_with_uptime("kill -KILL $(pgrep -x surf)", check=True)[0]

    def back(read: tuple[float, dict[str, str] | None, list[str]]) -> bool:
        """Whether a panel read shows the instance back with a new nonce.

        Args:
            read: the panel read, as (uptime, sample, titles).

        Returns:
            True if the instance is on the panel and the nonce is not the one before the kill.
        """
        return panel.on_panel(read[1]) and read[1]["nonce"] != before["nonce"]

    # The board uptime of the first read showing the page back, so it overstates by up to one
    # read plus the 0.5 s sleep.
    back_s, final = panel.wait_until(back, _GIVE_UP_SECONDS, every=0.5)
    recovered_s = round(final[0] - killed_at, 1) if back_s is not None else None

    record_property("before", before)
    record_property("after", final[1] if final else None)
    record_property("killed_at_uptime_s", killed_at)
    record_property("recovered_s", recovered_s)

    assert recovered_s is not None and recovered_s <= _BOUND_SECONDS, (
        f"back on the panel after {recovered_s} s (None: no sample on the panel carried a new nonce "
        f"within {_GIVE_UP_SECONDS} s); bound {_BOUND_SECONDS} s; last sample {final[1] if final else None!r}"
    )
