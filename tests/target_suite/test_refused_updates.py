"""Target suite: an image update not meant for the board is refused, and the board is left as it was."""

import configparser
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
from board import Board
from container_dir import ContainerDir
from panel import Panel
from update import Update

_FOREIGN_KEY_CN = "Refused update test key"
# only catches a hang, with the install tool's own checks and bundle server included;
# neither TST017 nor TST018 states a bound
_INSTALL_TIMEOUT_SECONDS = 120

pytestmark = pytest.mark.sends_update


class Bundles(NamedTuple):
    """The two refused bundles' paths, and the `compatible` the other-hardware one carries.

    Attributes:
        foreign_signature: the bundle signed by a key no operator holds.
        other_hardware: the operator-signed bundle for other hardware.
        other_hardware_compatible: the `compatible` the other-hardware bundle carries.
    """

    foreign_signature: Path
    other_hardware: Path
    other_hardware_compatible: str


@pytest.fixture(scope="module")
def bundles(request: pytest.FixtureRequest, board: Board) -> Bundles:
    """Build both refused bundles through `tools/kas-run.sh`; return their `Bundles`.

    No bundle is both operator-signed and carries the board's own `compatible`.

    Args:
        request: removes the build directory at the end of the module.
        board: the board under test, whose own `compatible` the bundles must not carry.

    Returns:
        The two bundles' paths and the `compatible` of the other-hardware one.
    """
    compatible = board.snapshot()["rauc_status"]["compatible"]
    # it is passed to the build container as an argument
    assert re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", compatible), (
        f"the board's compatible {compatible!r} is not a plain identifier"
    )
    work = ContainerDir(request)
    subprocess.run(
        [str(work.REPO / "tools" / "rauc-keygen.sh"), str(work.path / "foreign-key"), _FOREIGN_KEY_CN],
        check=True,
    )
    work.run("refused_bundles.sh", compatible)
    # refused_bundles.sh is the one owner of the other-hardware `compatible`
    manifest = configparser.ConfigParser()
    manifest.read(work.path / "other-hardware" / "manifest.raucm")
    return Bundles(
        work.path / "foreign-signature.raucb",
        work.path / "other-hardware.raucb",
        manifest["update"]["compatible"],
    )


@pytest.fixture
def update(board: Board, request: pytest.FixtureRequest, record_property: Callable[[str, object], None]) -> Update:
    """The `Update` that records the refused offer; it registers no undo.

    Args:
        board: the board under test.
        request: the test's request, whose test must carry `sends_update`.
        record_property: records the refused offer.

    Returns:
        The update, with `_INSTALL_TIMEOUT_SECONDS` as its timeout.
    """
    return Update(board, request, _INSTALL_TIMEOUT_SECONDS, record_property)


def test_foreign_signature(
    update: Update, panel: Panel, bundles: Bundles, record_property: Callable[[str, object], None]
) -> None:
    """TST017 foreign signature: offer an update signed by a key no operator holds; it is refused.

    Args:
        update: offers the bundle and judges the refusal.
        panel: the probe in the browser, waited on before and after so the instance is on the panel.
        bundles: the bundles built for the module.
        record_property: records the requirement.
    """
    record_property("requirement", "TST017")
    panel.wait_on_panel()
    update.refuse(bundles.foreign_signature, ("signature verification failed", "self-signed certificate"))
    panel.wait_on_panel()


def test_another_hardware_type(
    update: Update, panel: Panel, bundles: Bundles, record_property: Callable[[str, object], None]
) -> None:
    """TST018 another hardware type: offer an operator-signed update for other hardware; it is refused.

    Args:
        update: offers the bundle and judges the refusal.
        panel: the probe in the browser, waited on before and after so the instance is on the panel.
        bundles: the bundles built for the module.
        record_property: records the requirement.
    """
    record_property("requirement", "TST018")
    panel.wait_on_panel()
    update.refuse(bundles.other_hardware, ("Compatible mismatch", bundles.other_hardware_compatible))
    panel.wait_on_panel()
