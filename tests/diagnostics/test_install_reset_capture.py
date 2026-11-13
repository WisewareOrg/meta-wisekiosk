"""Diagnostics: a reset mid-install lands the board's pstore in that install's own output.

Runs `just kiosk-ota` against the board and crashes it with sysrq once
tools/kiosk-install.sh reports its kernel recorders armed, then checks that the same
output carries the reset and the board's pstore read back after it.

Outside the regression suite: it crashes the board on purpose, so it runs only when asked,
through the bench driver:

    bench test <ref> -- tests/diagnostics -k install_reset_capture -rP
"""

import subprocess
import threading
import time

ARMED = "[arm] armed: record_ftrace=1"
SEED_DELAY_SECONDS = 20
SEED = "echo c > /proc/sysrq-trigger"
_SSH = [
    "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10",
    "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=3",
]


def _crash(host):
    """Crash the board after `SEED_DELAY_SECONDS`, inside `rauc install`'s slot write.

    The crash takes the session down with it, so the ssh exit status says nothing; the
    test reads the outcome from kiosk-ota's own output instead.

    Args:
        host (str): `user@address` of the board.
    """
    time.sleep(SEED_DELAY_SECONDS)
    subprocess.run([*_SSH, host, SEED], timeout=60, check=False)


def test_install_reset_capture(target):
    """A crash mid-install leaves the panic and the ftrace ring in the install's output.

    Leaves the board on the slot it was on: the crashed install never activates the
    other one.
    """
    service = target.get_resource("NetworkService")
    host = f"{service.username}@{service.address}"
    ota = subprocess.Popen(
        ["just", "kiosk-ota", host],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    lines = []
    seed = None
    for line in ota.stdout:
        print(line, end="")
        lines.append(line)
        if seed is None and ARMED in line:
            seed = threading.Thread(target=_crash, args=(host,))
            seed.start()
    rc = ota.wait()
    if seed is not None:
        seed.join()
    output = "".join(lines)
    pstore = [line for line in lines if " [pstore] " in line]

    assert seed is not None, "the recorders never reported armed -- nothing was seeded"
    assert "watchdog_thresh=1" in output, "the soft-lockup threshold was not lowered"
    assert rc != 0, "kiosk-ota succeeded -- the seeded crash did not land mid-install"
    assert "board reset during install" in output, "the reset was not detected"
    assert any("== /sys/fs/pstore/dmesg-ramoops" in line for line in pstore), (
        "no dmesg-ramoops record in the read-back"
    )
    assert any("sysrq" in line.lower() for line in pstore), (
        "the read-back does not carry the seeded sysrq panic"
    )
    assert any("== /sys/fs/pstore/ftrace-ramoops" in line for line in pstore), (
        "no ftrace-ramoops record in the read-back"
    )
