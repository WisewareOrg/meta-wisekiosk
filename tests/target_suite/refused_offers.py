"""The updates the refused-update tests offer; none is both operator-signed and meant for this board."""

import configparser
import contextlib
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

from container_dir import ContainerDir

_FOREIGN_KEY_CN = "Refused update test key"


class Offer(NamedTuple):
    """An image update the board must refuse, and what its refusal must name.

    Attributes:
        bundle: the bundle on the host.
        reasons: text the refusal's output must carry, each.
    """

    bundle: Path
    reasons: tuple[str, ...]


class RefusedOffers(NamedTuple):
    """The two updates the board must refuse.

    Attributes:
        foreign_signature: signed by a key no operator holds.
        other_hardware: operator-signed, but for other hardware.
    """

    foreign_signature: Offer
    other_hardware: Offer

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
            Offer(work.path / "foreign-signature.raucb", ("signature verification failed", "self-signed certificate")),
            Offer(work.path / "other-hardware.raucb", ("Compatible mismatch", manifest["update"]["compatible"])),
        )
