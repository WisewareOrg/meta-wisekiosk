"""Target suite: an image update not meant for the board is refused, and the board is left as it was."""

import configparser
import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import NamedTuple

import pytest

_REPO = Path(__file__).resolve().parents[2]
_WORK_ROOT = _REPO / "build" / "refused-updates"
_CONTAINER_WORK_ROOT = "/work/build/refused-updates"
_FOREIGN_KEY_CN = "Refused update test key"
# only catches a hang; neither TST017 nor TST018 states a bound
_INSTALL_TIMEOUT_SECONDS = 60


def _board_compatible(board):
    """The `compatible` the board's own `rauc` reports."""
    stdout, _stderr, _returncode = board.run("rauc status --output-format=json", check=True)
    compatible = json.loads("\n".join(stdout))["compatible"]
    # it is passed to the build container as an argument
    assert re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", compatible), (
        f"the board's compatible {compatible!r} is not a plain identifier"
    )
    return compatible


class Bundles(NamedTuple):
    """The two refused bundles' paths, and the `compatible` the other-hardware one carries."""

    foreign_signature: Path
    other_hardware: Path
    other_hardware_compatible: str


@pytest.fixture(scope="module")
def bundles(request, board):
    """Build both refused bundles through `tools/kas-run.sh`; return their `Bundles`.

    No bundle is both operator-signed and carries the board's own `compatible`.
    """
    board_compatible = _board_compatible(board)
    run_dir = _WORK_ROOT / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    request.addfinalizer(lambda: shutil.rmtree(run_dir))

    subprocess.run(
        [str(_REPO / "tools" / "rauc-keygen.sh"), str(run_dir / "foreign-key"), _FOREIGN_KEY_CN],
        check=True,
    )
    container_dir = f"{_CONTAINER_WORK_ROOT}/{run_dir.name}"
    subprocess.run(
        [
            str(_REPO / "tools" / "kas-run.sh"),
            "shell",
            "kiosk-zero-w.yaml",
            "-c",
            f"bash /work/tests/target_suite/refused_bundles.sh {container_dir} {board_compatible}",
        ],
        cwd=_REPO,
        check=True,
    )
    # refused_bundles.sh is the one owner of the other-hardware `compatible`
    manifest = configparser.ConfigParser()
    manifest.read(run_dir / "other-hardware" / "manifest.raucm")
    return Bundles(
        run_dir / "foreign-signature.raucb",
        run_dir / "other-hardware.raucb",
        manifest["update"]["compatible"],
    )


def _snapshot(board):
    """What the next boot and the running build are, read from the board."""

    def read(cmd):
        return "\n".join(board.run(cmd, check=True)[0])

    return {
        "boot_variables": read("fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT"),
        "rauc_status": json.loads(read("rauc status --detailed --output-format=json")),
        "boot_id": read("cat /proc/sys/kernel/random/boot_id"),
        "commit": board.commit(),
    }


def _offer(request, board, bundle):
    """Copy `bundle` to the board's `/tmp`, run `rauc install` on it, and return rc, output and seconds."""
    remote = f"/tmp/refused-{bundle.name}"
    board.put(str(bundle), remote)
    request.addfinalizer(lambda: board.run(f"rm -f {remote}", check=True))
    started = time.monotonic()
    stdout, stderr, returncode = board.run(f"rauc install {remote}", timeout=_INSTALL_TIMEOUT_SECONDS)
    return returncode, "\n".join(stdout + stderr), round(time.monotonic() - started, 1)


def _assert_refused(request, board, panel, record_property, bundle, reasons):
    """Offer `bundle`; assert it was refused for each of `reasons`, nothing staged, same build, on the panel."""
    panel.wait_on_panel()
    before = _snapshot(board)
    record_property("before", json.dumps(before))
    returncode, output, duration_s = _offer(request, board, bundle)
    record_property("install_rc", returncode)
    record_property("install_output", output)
    record_property("install_s", duration_s)
    after = _snapshot(board)
    record_property("after", json.dumps(after))

    # rc 2 is a D-Bus error: the board could not say, which is not a refusal
    assert returncode == 1, f"rauc install returned {returncode}, not a refusal (1): {output}"
    for reason in reasons:
        assert reason in output, f"refused, but not for the reason {reason!r}: {output}"
    assert after["boot_variables"] == before["boot_variables"], "the next boot's slot order changed"
    assert after["rauc_status"] == before["rauc_status"], "rauc's slot status changed"
    assert after["boot_id"] == before["boot_id"], "the board restarted"
    assert after["commit"] == before["commit"], "the board runs a different build"
    panel.wait_on_panel()


def test_foreign_signature(request, board, panel, bundles, record_property):
    """TST017 foreign signature: offer an update signed by a key no operator holds; it is refused."""
    record_property("requirement", "TST017")
    _assert_refused(
        request,
        board,
        panel,
        record_property,
        bundles.foreign_signature,
        ("signature verification failed", "self-signed certificate"),
    )


def test_another_hardware_type(request, board, panel, bundles, record_property):
    """TST018 another hardware type: offer an operator-signed update for other hardware; it is refused."""
    record_property("requirement", "TST018")
    _assert_refused(
        request,
        board,
        panel,
        record_property,
        bundles.other_hardware,
        ("Compatible mismatch", bundles.other_hardware_compatible),
    )
