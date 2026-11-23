"""The base of every target-suite test class, the form of a parametrized case, and the replay mark."""

from collections.abc import Callable, Collection
from pathlib import Path

import pytest
from board import Board
from record import Record


class BoardTest:
    """A target-suite test class.

    Before each test, the autouse `_board_and_record` in this directory's conftest puts a new `Board` and
    the test's `Record` on the instance; pytest then runs the class's `setup_method`, if it has one.
    When the test ends, the board's `cleanup` undoes, last first, what `setup_method` and the test
    registered on it.

    Attributes:
        board: the board under test, for this test only.
        record: this test's record.
    """

    board: Board
    record: Record


def replaying(recording: Path) -> Callable[[Callable], Callable]:
    """Mark a test to replay `recording` through wisebench's `proxy` fixture, which its board reaches on demand.

    Args:
        recording: the replay set's directory, holding `flows.har` and `config.json`.

    Returns:
        What marks the test.
    """

    def mark(test: Callable) -> Callable:
        """Mark `test` to replay the recording.

        Args:
            test: the test.

        Returns:
            The test, marked.
        """
        test = pytest.mark.parametrize("proxy", [str(recording / "flows.har")], indirect=True, ids=[recording.name])(
            test
        )
        return pytest.mark.usefixtures("proxy")(test)

    return mark


def case(requirement: str, *values: object, marks: Collection[pytest.MarkDecorator] = ()) -> object:
    """One case of a parametrized test: the item it checks, first and as its id, then its values.

    Args:
        requirement: the TST item the case checks.
        *values: the case's other parameters, in order.
        marks: the case's marks.

    Returns:
        The case.
    """
    return pytest.param(requirement, *values, id=requirement, marks=marks)
