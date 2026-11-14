"""Target-suite setup: switch on the shared board setup for every test here."""

import hashlib
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from panel import Panel
from verdicts.context import display_mode, file_hashes, webkit_env

_CONFIG_PATH = "/data/config/config.json"
_CONFIG_COPY_PATH = "/tmp/kiosk-config.json"
_PROBE_SRC = Path(__file__).resolve().parent / "probe.js"
_PROBE_COPY_PATH = "/tmp/kiosk-probe.js"
_SURF_DIR = "/home/root/.surf"
_SURF_SCRIPT_PATH = f"{_SURF_DIR}/script.js"
_BROWSER_WAIT_SECONDS = 90
_BROWSER_POLL_SECONDS = 2
_HASHED_PATHS = (
    "/data/config/config.json",
    "/data/config/kiosk.conf",
    "/boot/config.txt",
    "/boot/cmdline.txt",
)


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(install_candidate):
    """Activate `install_candidate` (tests/conftest.py) for every test in this suite."""


@pytest.fixture
def set_config(request, board):
    """Build an `apply` that swaps the board onto a given config, undoing it at teardown.

    `apply(path)` stops the browser, clears a mount a dead run left over the live config path,
    copies `path` to the board, bind-mounts it over the live config, restarts the backend and
    waits for the page, then starts the browser. Each step's undo is registered with
    `request.addfinalizer` once that step has succeeded, so teardown runs them in reverse even
    if a later step fails -- except the backend restart's undo, registered right after the
    restart itself succeeds and before the page wait, so it still runs if that wait fails.
    Knows nothing of replay; any test may hand `apply` a config file. Call it at most once per
    test.

    Args:
        request (pytest.FixtureRequest): registers each step's undo.
        board (Board): the board under test (tests/conftest.py).

    Returns:
        Callable[[str | os.PathLike], None]: `apply(path)`.
    """

    def apply(path):
        """Swap the board onto `path`'s config and leave the instance running against it.

        Args:
            path (str | os.PathLike): the config file to copy to the board.
        """
        board.run("systemctl stop kiosk.service", check=True)
        request.addfinalizer(lambda: board.run("systemctl start kiosk.service", check=True))

        board.run(
            f"if grep -q ' {_CONFIG_PATH} ' /proc/self/mountinfo; then umount {_CONFIG_PATH}; fi",
            check=True,
        )

        board.put(str(path), _CONFIG_COPY_PATH)
        request.addfinalizer(lambda: board.run(f"rm -f {_CONFIG_COPY_PATH}", check=True))

        board.run(f"mount --bind {_CONFIG_COPY_PATH} {_CONFIG_PATH}", check=True)
        request.addfinalizer(lambda: board.run(f"umount {_CONFIG_PATH}", check=True))

        def _restart_backend_and_wait():
            board.run("systemctl restart wisekiosk.service", check=True)
            assert board.wait_for_page(), "page did not serve after the backend restart"

        board.run("systemctl restart wisekiosk.service", check=True)
        request.addfinalizer(_restart_backend_and_wait)
        assert board.wait_for_page(), "page did not serve after the backend restart"

        board.run("systemctl start kiosk.service", check=True)
        request.addfinalizer(lambda: board.run("systemctl stop kiosk.service", check=True))

    return apply


@pytest.fixture
def panel(request, board, record_property):
    """The on-the-panel observation: the probe loaded into the browser, undone at teardown.

    Copies `probe.js` to `/tmp`, bind-mounts it over surf's script path (clearing a mount a dead
    run left there) and restarts the browser so surf loads it. Each undo is registered with
    `request.addfinalizer` once its step has succeeded, except the browser restart's, registered
    before the bind mount so teardown unmounts the probe and then restarts the browser. Does not
    wait for the page; the test calls `Panel.wait_on_panel`.

    Args:
        request (pytest.FixtureRequest): registers each step's undo.
        board (Board): the board under test (tests/conftest.py).
        record_property (Callable[[str, object], None]): records the probe's sha256.

    Returns:
        Panel: the observation.
    """
    board.put(str(_PROBE_SRC), _PROBE_COPY_PATH)
    request.addfinalizer(lambda: board.run(f"rm -f {_PROBE_COPY_PATH}", check=True))

    board.run(f"mkdir -p {_SURF_DIR} && touch {_SURF_SCRIPT_PATH}", check=True)
    board.run(
        f"if grep -q ' {_SURF_SCRIPT_PATH} ' /proc/self/mountinfo; "
        f"then umount {_SURF_SCRIPT_PATH}; fi",
        check=True,
    )

    request.addfinalizer(lambda: board.run("systemctl restart kiosk.service", check=True))
    board.run(f"mount --bind {_PROBE_COPY_PATH} {_SURF_SCRIPT_PATH}", check=True)
    request.addfinalizer(lambda: board.run(f"umount {_SURF_SCRIPT_PATH}", check=True))

    board.run("systemctl restart kiosk.service", check=True)

    record_property("probe_sha256", hashlib.sha256(_PROBE_SRC.read_bytes()).hexdigest())
    return Panel(board)


def _utc_now():
    """The host's UTC time, ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="session")
def _device_facts(install_candidate, board):
    """The device context, read once after the install.

    Polls for the browser first: it starts some seconds after ssh does following a restart.

    Args:
        install_candidate: the session's install (tests/conftest.py).
        board (Board): the board under test.

    Returns:
        dict[str, object]: boot_id, uptime_s, kernel, the sha256 of the config, kiosk.conf,
            boot config and boot cmdline ("absent" when missing), the browser's cmdline sha256,
            its WEBKIT_* environment, the display mode, NTP sync state and the start time.

    Raises:
        AssertionError: the browser never appeared.
    """
    deadline = time.monotonic() + _BROWSER_WAIT_SECONDS
    while True:
        try:
            stdout, _stderr, returncode = board.run("pgrep -x surf")
        except subprocess.TimeoutExpired:
            stdout, returncode = [], 1
        if returncode == 0 and stdout:
            pid = stdout[0].strip()
            break
        assert time.monotonic() < deadline, "the browser never appeared"
        time.sleep(_BROWSER_POLL_SECONDS)

    def read(cmd):
        return "\n".join(board.run(cmd, check=True)[0]).strip()

    hashes_out, _, _ = board.run("sha256sum " + " ".join(_HASHED_PATHS))
    hashes = file_hashes("\n".join(hashes_out), _HASHED_PATHS)
    return {
        "boot_id": read("cat /proc/sys/kernel/random/boot_id"),
        "uptime_s": float(read("cat /proc/uptime").split()[0]),
        "kernel": read("uname -r"),
        "config_sha256": hashes["/data/config/config.json"],
        "kiosk_conf_sha256": hashes["/data/config/kiosk.conf"],
        "boot_config_sha256": hashes["/boot/config.txt"],
        "boot_cmdline_sha256": hashes["/boot/cmdline.txt"],
        "browser_cmdline_sha256": read(f"sha256sum /proc/{pid}/cmdline").split()[0],
        "browser_webkit_env": webkit_env(read(f"tr '\\0' '\\n' < /proc/{pid}/environ")),
        "display_mode": display_mode(read("DISPLAY=:0 xrandr")),
        "timesync": read("timedatectl show -p NTPSynchronized --value"),
        "start": _utc_now(),
    }


@pytest.fixture(autouse=True)
def device_context(_device_facts, record_property):
    """Record the device context on every test, and the end time after it.

    Args:
        _device_facts (dict[str, object]): the session's device facts.
        record_property (Callable[[str, object], None]): records each fact.
    """
    for key, value in _device_facts.items():
        record_property(key, value)
    yield
    record_property("end", _utc_now())
