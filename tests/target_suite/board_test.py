"""The base of every target-suite test class, and the form of a parametrized case."""

from collections.abc import Collection

import pytest
from board import Board
from record import Record


class BoardTest:
    """A target-suite test class.

    Before each test, `pytest_runtest_setup` in this directory's conftest puts a new `Board` and the
    test's `Record` on the instance; pytest then runs the class's `setup_method`, if it has one.
    When the test ends, the board's `cleanup` undoes, last first, what `setup_method` and the test
    registered on it.

    Attributes:
        board: the board under test, for this test only.
        record: this test's record.
    """

    board: Board
    record: Record


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
