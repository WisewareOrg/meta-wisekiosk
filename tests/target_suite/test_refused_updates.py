"""Target suite: an image update not meant for the board is refused, and the board is left as it was."""

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_WORK_ROOT = _REPO / "build" / "refused-updates"
_CONTAINER_WORK_ROOT = "/work/build/refused-updates"
# A sibling machine's `compatible`, as its `system.conf` in meta-autonomos-raspberrypi carries it.
_OTHER_HARDWARE_COMPATIBLE = "autonomos-raspberrypi-zero-2w"
_FOREIGN_KEY_CN = "Refused update test key"
# only catches a hang; neither TST017 nor TST018 states a bound
_INSTALL_TIMEOUT_SECONDS = 60
_PAYLOAD_BYTES = 1024 * 1024
# a picked ceiling on a hung container, so a hang cannot hold the whole bench run
_KAS_TIMEOUT_SECONDS = 900

# Runs inside the kas container. `rauc bundle` refuses a compressible payload (it squashes to
# 4096 bytes), hence random bytes. The operator's key is read from `update-bundle`'s own
# environment and never copied.
_BUILD_SCRIPT = """\
set -euo pipefail
cd {container_dir}
bitbake -e update-bundle > bitbake-env.txt
bb_var() {{ sed -n "s/^$1=\\"\\(.*\\)\\"$/\\1/p" bitbake-env.txt; }}
rauc_bin="$(bb_var STAGING_BINDIR_NATIVE)"
operator_key="$(bb_var RAUC_KEY_FILE)"
operator_cert="$(bb_var RAUC_CERT_FILE)"
: "${{rauc_bin:?}}" "${{operator_key:?}}" "${{operator_cert:?}}"
export PATH="$rauc_bin:$PATH"

make_bundle() {{
    name="$1"; compatible="$2"; key="$3"; cert="$4"
    mkdir "$name"
    printf '[update]\\ncompatible=%s\\n[bundle]\\nformat=verity\\n[image.rootfs]\\nfilename=rootfs.ext4\\n' \\
        "$compatible" > "$name/manifest.raucm"
    head -c {payload_bytes} /dev/urandom > "$name/rootfs.ext4"
    rauc bundle --cert="$cert" --key="$key" "$name" "$name.raucb"
}}

make_bundle foreign-signature {board_compatible} foreign-key/signing.key.pem foreign-key/signing.cert.pem
make_bundle other-hardware {other_hardware_compatible} "$operator_key" "$operator_cert"
"""


def _board_compatible(board):
    """The `compatible` the board's own `rauc` reports."""
    stdout, _stderr, _returncode = board.run("rauc status --output-format=json", check=True)
    return json.loads("\n".join(stdout))["compatible"]


@pytest.fixture(scope="module")
def bundles(request, board):
    """Build the two refused bundles through `tools/kas-run.sh`; return `(foreign_signature, other_hardware)` paths.

    The foreign-signature bundle carries the board's `compatible` and a throwaway key's signature.
    The other-hardware bundle carries the operator's signature and a `compatible` that is not the
    board's. The operator-signed bundle's `compatible` is the constant above in every case, so no
    bundle is both operator-signed and the board's own.
    """
    board_compatible = _board_compatible(board)
    assert board_compatible != _OTHER_HARDWARE_COMPATIBLE, (
        f"the board's compatible is {board_compatible!r}; the other-hardware bundle would be "
        "operator-signed and the board's own"
    )
    run_dir = _WORK_ROOT / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    request.addfinalizer(lambda: shutil.rmtree(run_dir))

    subprocess.run(
        [str(_REPO / "tools" / "rauc-keygen.sh"), str(run_dir / "foreign-key"), _FOREIGN_KEY_CN],
        check=True,
        capture_output=True,
    )
    container_dir = f"{_CONTAINER_WORK_ROOT}/{run_dir.name}"
    script = _BUILD_SCRIPT.format(
        container_dir=container_dir,
        payload_bytes=_PAYLOAD_BYTES,
        board_compatible=board_compatible,
        other_hardware_compatible=_OTHER_HARDWARE_COMPATIBLE,
    )
    (run_dir / "build.sh").write_text(script)
    subprocess.run(
        [
            str(_REPO / "tools" / "kas-run.sh"),
            "shell",
            "kiosk-zero-w.yaml",
            "-c",
            f"bash {container_dir}/build.sh",
        ],
        cwd=_REPO,
        check=True,
        timeout=_KAS_TIMEOUT_SECONDS,
    )
    return run_dir / "foreign-signature.raucb", run_dir / "other-hardware.raucb"


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
    remote = f"/tmp/{bundle.name}"
    board.put(str(bundle), remote)
    request.addfinalizer(lambda: board.run(f"rm -f {remote}", check=True))
    started = time.monotonic()
    stdout, stderr, returncode = board.run(f"rauc install {remote}", timeout=_INSTALL_TIMEOUT_SECONDS)
    return returncode, "\n".join(stdout + stderr), round(time.monotonic() - started, 1)


def _refuse(request, board, panel, record_property, bundle, reasons):
    """Offer `bundle`; assert it was refused for each of `reasons`, nothing staged, same build, on the panel."""
    panel.wait_on_panel()
    before = _snapshot(board)
    returncode, output, duration_s = _offer(request, board, bundle)
    after = _snapshot(board)
    record_property("install_rc", returncode)
    record_property("install_output", output)
    record_property("install_s", duration_s)
    record_property("before", json.dumps(before))
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
    _refuse(
        request,
        board,
        panel,
        record_property,
        bundles[0],
        ("signature verification failed", "self-signed certificate"),
    )


def test_another_hardware_type(request, board, panel, bundles, record_property):
    """TST018 another hardware type: offer an operator-signed update for other hardware; it is refused."""
    record_property("requirement", "TST018")
    _refuse(
        request,
        board,
        panel,
        record_property,
        bundles[1],
        ("Compatible mismatch", _OTHER_HARDWARE_COMPATIBLE),
    )
