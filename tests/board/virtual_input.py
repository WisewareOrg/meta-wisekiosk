"""A virtual input device on the board, made with evemu."""

import tempfile
from pathlib import Path

from board.part import Part


class VirtualInput(Part):
    """A virtual input device, made on the board with evemu and gone when the test ends."""

    def _put(self, directory: str, files: dict[str, str]) -> None:
        """Put evemu and `files` in `directory` on the board, and load uinput, each until the test ends.

        Args:
            directory: the directory, made anew.
            files: each file's text, by name.
        """
        helpers = self._board.fixture("evemu_helpers")
        self._board.cleanup.callback(self._board.run, f"rm -rf {directory}")
        self._board.run(f"rm -rf {directory}; mkdir {directory}", check=True)
        uinput_loaded = self._board.run("test -d /sys/module/uinput").returncode == 0
        self._board.run("modprobe uinput", check=True)
        if not uinput_loaded:
            self._board.cleanup.callback(self._board.run, "rmmod uinput", check=True)
        with tempfile.TemporaryDirectory() as host_directory:
            for name, text in files.items():
                path = Path(host_directory) / name
                path.write_text(text)
                self._board.put(str(path), f"{directory}/{name}")
        for name in helpers.sha256:
            self._board.put(str(helpers.directory / name), f"{directory}/{name}")
        self._board.run("chmod 0755 " + " ".join(f"{directory}/{name}" for name in helpers.sha256), check=True)
