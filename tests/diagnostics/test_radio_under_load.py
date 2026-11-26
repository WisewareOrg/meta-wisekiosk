"""Diagnostics: the board's radio across the network load TST008 applies.

Reads the board's radio, applies TST008's load with `Network.load`, and reads the radio again. It
records the load's rate and `Radio.properties` of the two reads: the signal at each edge and the
counters' deltas across the window, or why there are none. It judges nothing.

Outside the regression suite: it reads the board and loads its network, and changes nothing on it, so
it runs by hand on a running board, through the bench driver:

    bench test <ref> --skip-build -- tests/diagnostics -k radio_under_load -rP
"""

from collections.abc import Callable

from board import Board
from board.network import Radio

# the length of TST008's load
LOAD_SECONDS = 60


def test_radio_under_load(board: Board, record_property: Callable[[str, object], None]) -> None:
    """The board's radio before and after TST008's load, and the load's rate.

    Args:
        board: the board under test.
        record_property: records the load's rate and the radio's properties.
    """
    before = board.network.radio()
    with board.network.load(seconds=LOAD_SECONDS) as load:
        pass
    after = board.network.radio()

    record_property("load_mb_s", round(load.mb_s, 2))
    for name, value in Radio.properties(before, after).items():
        record_property(name, value)
