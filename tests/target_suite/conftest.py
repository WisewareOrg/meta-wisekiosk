"""Target-suite setup: switch on the shared board setup for every test here."""

import hashlib
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

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
_PANEL_WAIT_SECONDS = 90
_PANEL_POLL_SECONDS = 1
OWN_ORIGINS = ("http://localhost:8080", "http://127.0.0.1:8080")
_PROBE_FIELDS = ("nonce", "state", "cards", "origin")
_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')
_TITLES_WALK = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
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


def _probe_sample(xprop_output):
    """The first window title carrying the probe's four fields, as a dict of strings, else None."""
    for line in xprop_output.splitlines():
        match = _WM_NAME.match(line)
        if match and "WK1 " in match.group(1):
            tokens = match.group(1).split("WK1 ", 1)[1].split()
            found = dict(token.split("=", 1) for token in tokens if "=" in token)
            if all(key in found for key in _PROBE_FIELDS):
                return {key: found[key] for key in _PROBE_FIELDS}
    return None


class Panel:
    """What the panel shows, read through the probe the `panel` fixture puts in the browser."""

    def __init__(self, board):
        self._board = board

    @staticmethod
    def on_panel(sample):
        """The app applied, served by the board's own backend; the card count is never judged."""
        return sample is not None and sample["state"] == "applied" and sample["origin"] in OWN_ORIGINS

    def read(self):
        """The board's uptime and the probe's sample (None = no payload), from one command.

        Raises:
            subprocess.TimeoutExpired: the command ran past `Board.run`'s timeout.
        """
        stdout, _stderr, _returncode = self._board.run(f"cat /proc/uptime; {_TITLES_WALK}")
        return float(stdout[0].split()[0]), _probe_sample("\n".join(stdout[1:]))

    def wait_on_panel(self, timeout_s=_PANEL_WAIT_SECONDS):
        """Poll until the instance is on the panel; return that read's (uptime, sample)."""
        deadline = time.monotonic() + timeout_s
        while True:
            uptime_s, sample = self.read()
            if self.on_panel(sample):
                return uptime_s, sample
            assert time.monotonic() < deadline, (
                f"the instance was not on the panel within {timeout_s} s; last sample: {sample!r}"
            )
            time.sleep(_PANEL_POLL_SECONDS)


@pytest.fixture
def panel(request, board, record_property):
    """Load the probe into the browser and return a `Panel`; the page wait is the test's.

    The probe is copied to `/tmp` and bind-mounted over surf's script path, then the browser
    restarts to load it. Each undo is registered once its step has succeeded, except the
    browser restart's, registered before the bind mount so teardown unmounts the probe, then
    restarts the browser, then removes the copy.
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
    return datetime.now(timezone.utc).isoformat()


def _browser_pid(board):
    """The browser's pid; it starts some seconds after ssh does following a restart."""
    deadline = time.monotonic() + _BROWSER_WAIT_SECONDS
    while True:
        try:
            stdout, _stderr, returncode = board.run("pgrep -x surf")
        except subprocess.TimeoutExpired:
            stdout, returncode = [], 1
        if returncode == 0 and stdout:
            return stdout[0].strip()
        assert time.monotonic() < deadline, "the browser never appeared"
        time.sleep(_BROWSER_POLL_SECONDS)


@pytest.fixture(autouse=True)
def device_context(board, record_property):
    """Record the board as the test found it, and the end time after the test.

    Facts are raw board output: a missing file is simply absent from `file_sha256`.
    """
    pid = _browser_pid(board)

    def read(cmd):
        return "\n".join(board.run(cmd, check=True)[0]).strip()

    sums_out, sums_err, sums_rc = board.run("sha256sum " + " ".join(_HASHED_PATHS))
    assert sums_rc in (0, 1), f"sha256sum failed (rc {sums_rc}): {chr(10).join(sums_err)}"
    environ = read(f"tr '\\0' '\\n' < /proc/{pid}/environ").splitlines()
    xrandr = read("DISPLAY=:0 xrandr").splitlines()
    facts = {
        "boot_id": read("cat /proc/sys/kernel/random/boot_id"),
        "uptime_s": float(read("cat /proc/uptime").split()[0]),
        "kernel": read("uname -r"),
        "file_sha256": "\n".join(sums_out),
        "browser_cmdline_sha256": read(f"sha256sum /proc/{pid}/cmdline").split()[0],
        "browser_webkit_env": ",".join(line for line in environ if line.startswith("WEBKIT_")),
        "display_mode": next((line.strip() for line in xrandr if "*" in line), ""),
        "timesync": read("timedatectl show -p NTPSynchronized --value"),
        "start": _utc_now(),
    }
    for key, value in facts.items():
        record_property(key, value)
    yield
    record_property("end", _utc_now())
