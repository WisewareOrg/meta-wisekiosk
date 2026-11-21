"""Offering an image update to the board, and reading what the board would boot next."""

import json
import pathlib
import subprocess
import time

_INSTALL_TOOL = pathlib.Path(__file__).resolve().parents[2] / "tools" / "kiosk-install.sh"


def snapshot(board):
    """What the next boot and the running build are, read from the board."""

    def read(cmd):
        return "\n".join(board.run(cmd, check=True)[0])

    return {
        "boot_variables": read("fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT"),
        "rauc_status": json.loads(read("rauc status --detailed --output-format=json")),
        "boot_id": read("cat /proc/sys/kernel/random/boot_id"),
        "commit": board.commit(),
    }


def install(request, board, bundle, timeout):
    """Install `bundle` through `tools/kiosk-install.sh`, the board's one install path.

    Args:
        request (pytest.FixtureRequest): records the board's `mem_available_kb` before the
            install as a property of the test.
        board (Board): the board under test (tests/conftest.py).
        bundle (pathlib.Path): the bundle on the host.
        timeout (float): the longest the install may take.

    Returns:
        tuple[int, str, float]: the tool's return code, its combined stdout and stderr, and
            the seconds it took.

    Raises:
        subprocess.TimeoutExpired: the install ran past `timeout`.
    """
    meminfo = board.run("cat /proc/meminfo", check=True)[0]
    available_kb = next(line.split()[1] for line in meminfo if line.startswith("MemAvailable:"))
    request.node.user_properties.append(("mem_available_kb", available_kb))
    started = time.monotonic()
    result = subprocess.run(
        [str(_INSTALL_TOOL), board.host, str(bundle)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout + result.stderr, round(time.monotonic() - started, 1)
