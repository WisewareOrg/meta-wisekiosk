"""The base of every target-suite test class."""

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
