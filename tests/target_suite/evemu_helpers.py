"""evemu-tools and its library, built for the board in the kas build container."""

import contextlib
import hashlib
from pathlib import Path
from typing import NamedTuple

from container_dir import ContainerDir


class EvemuHelpers(NamedTuple):
    """The built evemu files' directory, and what was built.

    Attributes:
        directory: where the built files are.
        sha256: each built file's sha256, by name.
    """

    directory: Path
    sha256: dict

    @classmethod
    def build(cls, cleanup: contextlib.ExitStack) -> "EvemuHelpers":
        """Build evemu-tools and its library under `build/keyboard/` through `tools/kas-run.sh`.

        Args:
            cleanup: removes the work directory when it unwinds.

        Returns:
            The built files and what was built.
        """
        work = ContainerDir(cleanup, "keyboard")
        work.run_script("evemu_tools.sh")
        directory = work.path / "helpers"
        return cls(
            directory,
            {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(directory.iterdir())},
        )
