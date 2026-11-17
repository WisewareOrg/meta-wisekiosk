"""Offering an image update to the board, and reading what the board would boot next."""

import json
import time


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
    """Copy `bundle` to the board's `/tmp`, run `rauc install` on it, and return rc, output and seconds.

    Args:
        request (pytest.FixtureRequest): registers the removal of the board's copy, and records
            the board's `mem_available_kb` before the copy as a property of the test.
        board (Board): the board under test (tests/conftest.py).
        bundle (pathlib.Path): the bundle on the host.
        timeout (float): the longest `rauc install` may take.

    Returns:
        tuple[int, str, float]: the return code, the combined stdout and stderr, and the seconds
            `rauc install` took.

    Raises:
        subprocess.TimeoutExpired: `rauc install` ran past `timeout`.
    """
    remote = f"/tmp/{bundle.name}"
    meminfo = board.run("cat /proc/meminfo", check=True)[0]
    available_kb = next(line.split()[1] for line in meminfo if line.startswith("MemAvailable:"))
    request.node.user_properties.append(("mem_available_kb", available_kb))
    board.put(str(bundle), remote)
    request.addfinalizer(lambda: board.run(f"rm -f {remote}", check=True))
    started = time.monotonic()
    stdout, stderr, returncode = board.run(f"rauc install {remote}", timeout=timeout)
    return returncode, "\n".join(stdout + stderr), round(time.monotonic() - started, 1)
