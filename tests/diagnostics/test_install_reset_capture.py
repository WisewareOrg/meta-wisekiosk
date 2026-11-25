"""Diagnostics: a reset mid-install lands the board's pstore in that install's own output.

Runs `just kiosk-ota` against the board and crashes it with sysrq once rauc reports it is
writing the slot, then checks that the same output carries the reset and the board's pstore
read back after it, and that a line the kernel logged before the crash is in both the live
kernel stream and the read-back's panic record.

Outside the regression suite: it crashes the board on purpose, so it runs only when asked,
through the bench driver:

    bench test <ref> -- tests/diagnostics -k install_reset_capture -rP
"""

import subprocess
import uuid

from board import Board

RAUC_TAG = "rauc["
SLOT_WRITE = "writing data to device"
PSTORE_HEADER = " [pstore] == /sys/fs/pstore/"


def _section(pstore: list[str], record: str) -> list[str]:
    """Collect the lines the read-back printed under the pstore records named `record`.

    Args:
        pstore: the install's `[pstore]` lines.
        record: the start of the record names to collect, such as `dmesg-ramoops`.

    Returns:
        The lines between each matching record's header and the next header.
    """
    section = []
    inside = False
    for line in pstore:
        if PSTORE_HEADER in line:
            inside = line.split(PSTORE_HEADER, 1)[1].startswith(record)
        elif inside:
            section.append(line)
    return section


def test_install_reset_capture(board: Board) -> None:
    """A crash mid-install leaves the panic and the console in the install's output.

    The crashed install never activates the slot it was writing, so the board comes back
    on the slot it booted from before.

    Args:
        board: the board under test, crashed mid-install.
    """
    slot_before = board.updates.rauc_status()["booted"]
    marker = str(uuid.uuid4())
    seed = f"echo {marker} > /dev/kmsg; sleep 3; echo c > /proc/sysrq-trigger"

    ota = subprocess.Popen(
        ["just", "kiosk-ota", board.host],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines = []
    seeded = False
    for line in ota.stdout:
        print(line, end="")
        lines.append(line.rstrip("\n"))
        if not seeded and RAUC_TAG in line and SLOT_WRITE in line:
            # its own ssh, apart from the SSHDriver
            subprocess.Popen(
                [*board.fresh_ssh_argv(*Board.FAULT_SSH_OPTIONS), seed],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            seeded = True
    rc = ota.wait()
    output = "\n".join(lines)
    pstore = [line for line in lines if " [pstore] " in line]

    assert seeded, "rauc never reported writing the slot -- nothing was seeded"
    assert rc != 0, "kiosk-ota succeeded -- the seeded crash did not land mid-install"
    assert "board reset during install" in output, "the reset was not detected"
    assert any(" [kernel] " in line and marker in line for line in lines), "the marker is not in the live kernel stream"
    assert any(marker in line for line in _section(pstore, "dmesg-ramoops")), (
        "the marker is not in the read-back's dmesg-ramoops record"
    )
    assert any(line.endswith("== /sys/fs/pstore/console-ramoops-0") for line in pstore), (
        "no console-ramoops record in the read-back"
    )

    board.disconnect()
    board.connect()
    assert board.updates.rauc_status()["booted"] == slot_before, "the board did not come back on its own slot"
