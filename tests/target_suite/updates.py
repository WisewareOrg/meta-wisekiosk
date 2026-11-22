"""Offering an image update to the board, and reading what the board would boot next."""

import json
import os
import pathlib
import signal
import subprocess
import time

_INSTALL_TOOL = pathlib.Path(__file__).resolve().parents[2] / "tools" / "kiosk-install.sh"
# how long the tool may take to clean up after a SIGTERM
_CLEANUP_SECONDS = 120


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
        request (pytest.FixtureRequest): the test's request; its test must carry the
            `sends_update` marker, which orders it after every test that does not.
        board (Board): the board under test (tests/conftest.py).
        bundle (pathlib.Path): the bundle on the host.
        timeout (float): the longest the install may take.

    Returns:
        tuple[int, str, float]: the tool's return code, its combined stdout and stderr, and
            the seconds it took.

    Raises:
        AssertionError: the test is not marked `sends_update`.
        subprocess.TimeoutExpired: the install ran past `timeout`.
    """
    assert request.node.get_closest_marker("sends_update"), (
        f"{request.node.nodeid} sends an update but is not marked sends_update"
    )
    started = time.monotonic()
    tool = subprocess.Popen(
        [str(_INSTALL_TOOL), board.host, str(bundle)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = tool.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # the whole group, so the ssh running the install exits with the tool
        os.killpg(tool.pid, signal.SIGTERM)
        tool.communicate(timeout=_CLEANUP_SECONDS)
        raise
    return tool.returncode, output, round(time.monotonic() - started, 1)
