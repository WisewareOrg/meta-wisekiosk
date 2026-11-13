"""Diagnostics: a reset mid-install lands the board's pstore in that install's own output.

Runs `just kiosk-ota` against the board and crashes it with sysrq once rauc reports it is
writing the slot, then checks that the same output carries the armed recorders, the reset,
and the board's pstore read back after it.

Outside the regression suite: it crashes the board on purpose, so it runs only when asked,
through the bench driver:

    bench test <ref> -- tests/diagnostics -k install_reset_capture -rP
"""

import re
import subprocess

SLOT_WRITE = "rauc["
SLOT_WRITE_MESSAGE = "writing data to device"
ARMED = re.compile(
    r"\[arm\] armed: record_ftrace=1 filter_entries=\d+ watchdog_thresh=1 softlockup_panic=1$"
)
SEED = "echo c > /proc/sysrq-trigger"
CAPTURE_STREAM = "dmesg -w --time-format iso"


def _booted_slot(driver):
    """The slot the board booted from, as `rauc status` names it.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.

    Returns:
        str: the `Booted from:` line.

    Raises:
        AssertionError: `rauc status` failed or named no booted slot.
    """
    stdout, _stderr, returncode = driver.run("rauc status")
    assert returncode == 0, "rauc status failed"
    line = next((entry for entry in stdout if entry.startswith("Booted from:")), None)
    assert line is not None, f"no booted slot in rauc status:\n{chr(10).join(stdout)}"
    return line


def _crash(host):
    """Crash the board with sysrq.

    A plain ssh rather than the SSHDriver: the crash takes the connection down with it,
    and the driver's shared connection would have to be torn down mid-command.

    Args:
        host (str): `user@address` of the board.
    """
    subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
         "-o", "UserKnownHostsFile=/dev/null", "-o", "ServerAliveInterval=2",
         "-o", "ServerAliveCountMax=3", host, SEED],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )


def test_install_reset_capture(target):
    """A crash mid-install leaves the panic and the ftrace ring in the install's output.

    The crashed install never activates the slot it was writing, so the board comes back
    on the slot it booted from before.
    """
    service = target.get_resource("NetworkService")
    host = f"{service.username}@{service.address}"
    driver = target.get_driver("SSHDriver")
    slot_before = _booted_slot(driver)

    ota = subprocess.Popen(
        ["just", "kiosk-ota", host],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    lines = []
    seeded = False
    for line in ota.stdout:
        print(line, end="")
        lines.append(line.rstrip("\n"))
        if not seeded and SLOT_WRITE in line and SLOT_WRITE_MESSAGE in line:
            _crash(host)
            seeded = True
    rc = ota.wait()
    output = "\n".join(lines)
    pstore = [line for line in lines if " [pstore] " in line]

    assert any(ARMED.search(line) for line in lines), "the recorders did not all report armed"
    assert seeded, "rauc never reported writing the slot -- nothing was seeded"
    assert rc != 0, "kiosk-ota succeeded -- the seeded crash did not land mid-install"
    assert "board reset during install" in output, "the reset was not detected"
    assert any(line.endswith("== /sys/fs/pstore/dmesg-ramoops-0") for line in pstore), (
        "no dmesg-ramoops record in the read-back"
    )
    assert any("sysrq triggered crash" in line for line in pstore), (
        "the read-back does not carry the seeded panic"
    )
    assert any(line.endswith("== /sys/fs/pstore/ftrace-ramoops-0") for line in pstore), (
        "no ftrace-ramoops record in the read-back"
    )
    orphans = subprocess.run(["pgrep", "-f", CAPTURE_STREAM], capture_output=True, text=True)
    assert orphans.stdout == "", f"capture streams outlived the install: {orphans.stdout}"

    target.deactivate(driver)
    target.activate(driver)
    assert _booted_slot(driver) == slot_before, "the board did not come back on its own slot"
