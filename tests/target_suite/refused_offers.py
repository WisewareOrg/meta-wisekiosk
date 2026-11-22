"""The updates the refused-update tests offer; none is both operator-signed and meant for this board."""

import configparser
import contextlib
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

from container_dir import ContainerDir

_FOREIGN_KEY_CN = "Refused update test key"


class RefusedOffers(NamedTuple):
    """The two refused bundles, and the `compatible` the other-hardware one carries.

    Attributes:
        foreign_signature: a bundle signed by a key no operator holds.
        other_hardware: an operator-signed bundle for other hardware.
        other_hardware_compatible: the `compatible` the other-hardware bundle carries.
    """

    foreign_signature: Path
    other_hardware: Path
    other_hardware_compatible: str

    @classmethod
    def build(cls, cleanup: contextlib.ExitStack, board_compatible: str) -> "RefusedOffers":
        """Build both bundles under `build/refused-updates/` through `tools/kas-run.sh`.

        Args:
            cleanup: removes the work directory when it unwinds.
            board_compatible: the `compatible` the board's own `rauc` reports.

        Returns:
            The bundles.
        """
        # it is passed to the build container as an argument
        assert re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", board_compatible), (
            f"the board's compatible {board_compatible!r} is not a plain identifier"
        )
        work = ContainerDir(cleanup, "refused-updates")
        subprocess.run(
            [str(ContainerDir.REPO / "tools" / "rauc-keygen.sh"), str(work.path / "foreign-key"), _FOREIGN_KEY_CN],
            check=True,
        )
        work.run_script("refused_bundles.sh", board_compatible)
        # refused_bundles.sh is the one owner of the other-hardware `compatible`
        manifest = configparser.ConfigParser()
        manifest.read(work.path / "other-hardware" / "manifest.raucm")
        return cls(
            work.path / "foreign-signature.raucb",
            work.path / "other-hardware.raucb",
            manifest["update"]["compatible"],
        )
