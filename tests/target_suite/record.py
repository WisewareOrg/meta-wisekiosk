"""One test's recorded properties."""

from collections.abc import Callable


class Record:
    """One test's recorded properties, written where pytest's `record_property` writes them.

    A call records its keyword arguments in the order they are written, so the record's names, values
    and order are the calls'.
    """

    def __init__(self, record_property: Callable[[str, object], None]) -> None:
        """Bind to the test's property writer.

        Args:
            record_property: writes one property of the test being recorded.
        """
        self._record_property = record_property

    def __call__(self, **properties: object) -> None:
        """Record each property, in the order given.

        Args:
            **properties: the properties to record, by name.
        """
        for name, value in properties.items():
            self._record_property(name, value)
