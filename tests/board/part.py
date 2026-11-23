"""The base of every sub-part of the board, and how a stimulus that did not take fails a test."""

import contextlib
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from board import Board


class Part:
    """One sub-part of the board, which reaches the board through `self._board`."""

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board


@contextlib.contextmanager
def invalid_if(what: str) -> Iterator[None]:
    """Fail an assertion inside as an invalid check, not an appliance failure: the stimulus did not take.

    Args:
        what: how the stimulus did not take.

    Yields:
        None: the checks that the stimulus took run.

    Raises:
        AssertionError: a check inside failed; the message says the check is invalid, and why.
    """
    try:
        yield
    except AssertionError as error:
        why = f" ({error})" if str(error) else ""
        raise AssertionError(f"INVALID CHECK, not an appliance failure: {what}{why}") from None
