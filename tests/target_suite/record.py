"""One test's recorded properties, written through pytest's `record_property`."""

from collections.abc import Callable


class Record:
    """One test's recorded properties, written through pytest's `record_property`.

    Every property the target suite records goes through one `Record`: the test calls it, and
    `Panel`, `Backend` and `Update` hold it. A call records its keyword arguments in the order they
    are written, so a run of properties is one call, and the record's names, values and order are
    the calls'. `verdict` records `validity` from a check's problems.
    """

    def __init__(self, record_property: Callable[[str, object], None]) -> None:
        """Bind to the test's `record_property`.

        Args:
            record_property: pytest's fixture for the test being recorded.
        """
        self._record_property = record_property

    def __call__(self, **properties: object) -> None:
        """Record each property, in the order given.

        Args:
            **properties: the properties to record, by name.
        """
        for name, value in properties.items():
            self._record_property(name, value)

    def verdict(self, problems: list[str]) -> None:
        """Record `validity`: `valid` with no problems, else `invalid: ` and the problems joined by `; `.

        Args:
            problems: what makes the check invalid; empty when it is valid.
        """
        self(validity="valid" if not problems else f"invalid: {'; '.join(problems)}")
