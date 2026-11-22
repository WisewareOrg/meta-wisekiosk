"""The system journal's test markers."""

from board.part import Part


class Journal(Part):
    """The board's system journal, as the tests mark it and read the marks back."""

    def write_marker(self, text: str) -> None:
        """Write `text` to the board's journal under the identifier `kiosk-log-marker`.

        Args:
            text: the marker line.
        """
        self._board.run(f"echo {text} | systemd-cat -t kiosk-log-marker", check=True)

    def markers(self) -> list[str] | None:
        """Read the marker lines written to the journal under the identifier `kiosk-log-marker`.

        Returns:
            The lines, or None if `journalctl` returned nonzero.
        """
        result = self._board.run("journalctl -t kiosk-log-marker -o cat")
        return result.stdout if result.returncode == 0 else None
