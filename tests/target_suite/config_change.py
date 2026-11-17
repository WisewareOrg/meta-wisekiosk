"""The configuration change TST019 and TST020 hold across a restart: write it, read it back, undo it."""

import hashlib
import json
from pathlib import Path

CONFIG_PATH = "/data/config/config.json"
_CHANGED_KEY = "edge_band"
_CHANGED_VALUE = 5


class ConfigChange:
    """`edge_band` changed to 5 in the board's live config, and the steps that undo it.

    The file's contents are site configuration and never reach a record: only hashes do.

    Attributes:
        written_sha256 (str | None): sha256 of the bytes `apply` wrote; None before it runs.
    """

    def __init__(self, board, saved_dir):
        """Args:
        board (Board): the board under test.
        saved_dir (str | os.PathLike): host directory that holds the board's original file.
        """
        self._board = board
        self._saved = Path(saved_dir) / "config.json"
        self.written_sha256 = None

    def apply(self):
        """Save the board's config to the host, then write it back with `edge_band` changed."""
        self._board.get(CONFIG_PATH, str(self._saved))
        cfg = json.loads(self._saved.read_text())
        cfg[_CHANGED_KEY] = _CHANGED_VALUE
        written = self._saved.with_name("changed.json")
        data = (json.dumps(cfg, indent=2) + "\n").encode()
        written.write_bytes(data)
        self._board.put(str(written), CONFIG_PATH)
        self.written_sha256 = hashlib.sha256(data).hexdigest()

    def held_sha256(self):
        """The sha256 of the live config on the board, or None if `sha256sum` fails (file missing)."""
        stdout, _stderr, returncode = self._board.run(f"sha256sum {CONFIG_PATH}")
        if returncode != 0:
            return None
        return stdout[0].split()[0]

    def restore(self):
        """Put the saved original back, restart the backend and the browser, check the hash.

        Raises:
            AssertionError: the page is not served after the backend restart, or the board's
                hash is not the saved original's.
        """
        board = self._board
        board.put(str(self._saved), CONFIG_PATH)
        board.run("systemctl restart wisekiosk.service", check=True)
        assert board.wait_for_page(), "page did not serve after the backend restart"
        board.run("systemctl restart kiosk.service", check=True)
        expected = hashlib.sha256(self._saved.read_bytes()).hexdigest()
        held = self.held_sha256()
        assert held == expected, f"restored config hash {held}, expected the original's {expected}"
