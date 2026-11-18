"""Target-suite setup: switch on the shared board setup for every test here."""

import subprocess
import time
from datetime import datetime, timezone

import pytest

from outage import Outage
from panel import Panel

_CONFIG_COPY_PATH = "/tmp/kiosk-config.json"
_BROWSER_WAIT_SECONDS = 90
_BROWSER_POLL_SECONDS = 2
_HASHED_PATHS = (
    "/data/config/kiosk.conf",
    "/boot/config.txt",
    "/boot/cmdline.txt",
)


@pytest.fixture(scope="session")
def config_across_update(request, board, bench_candidate):
    """Hash the board's config before and after `install_candidate`; writes nothing.

    First unmounts a bind mount a dead run left over the live config path.

    Args:
        request (pytest.FixtureRequest): runs `install_candidate` between the two hashes.
        board (Board): the board under test (tests/conftest.py).
        bench_candidate (str | None): the commit under test, or None outside a build.

    Returns:
        tuple[str | None, str | None, str | None] | None: the sha256 of the live config before
            the install, after it, and of the image default after it (each None if the file is
            missing); None when there is no candidate to install.
    """
    board.unmount_if_mounted(board.CONFIG_PATH)
    if bench_candidate is None:
        request.getfixturevalue("install_candidate")
        return None
    before = board.sha256(board.CONFIG_PATH)
    request.getfixturevalue("install_candidate")
    return before, board.sha256(board.CONFIG_PATH), board.sha256(board.DEFAULT_CONFIG_PATH)


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(config_across_update):
    """Activate `install_candidate` (tests/conftest.py) for every test in this suite, via `config_across_update`."""


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

        board.unmount_if_mounted(board.CONFIG_PATH)

        board.put(str(path), _CONFIG_COPY_PATH)
        request.addfinalizer(lambda: board.run(f"rm -f {_CONFIG_COPY_PATH}", check=True))

        board.run(f"mount --bind {_CONFIG_COPY_PATH} {board.CONFIG_PATH}", check=True)
        request.addfinalizer(lambda: board.run(f"umount {board.CONFIG_PATH}", check=True))

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
    """Load the probe into the browser and return the `Panel`; the page wait is the test's."""
    observation = Panel(board)
    record_property("probe_sha256", observation.install(request))
    return observation


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

    hashed = " ".join((board.CONFIG_PATH, *_HASHED_PATHS))
    sums_out, sums_err, sums_rc = board.run("sha256sum " + hashed)
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


@pytest.fixture
def outage(board):
    """The `Outage` for the board; the test arms it."""
    return Outage(board)


_POWER_OFF_SECONDS = 10
_BOOT_ID_CMD = "cat /proc/sys/kernel/random/boot_id"


@pytest.fixture
def power_cut(target, board, request, record_property):
    """Return `cut()`, which cuts and restores the board's power and returns the host `time.monotonic()` at which power returned.

    Power is switched on again at teardown.
    """
    power = target.get_driver("PowerProtocol")
    request.addfinalizer(power.on)

    def cut():
        old_boot_id = board.run(_BOOT_ID_CMD, check=True)[0][0]
        board.disconnect()
        try:
            power.off()
            time.sleep(_POWER_OFF_SECONDS)
            on_began = time.monotonic()
            power.on()
        except subprocess.CalledProcessError as error:
            pytest.exit(f"the bench's power switch failed: {error}", returncode=1)
        restored = time.monotonic()
        record_property("power_on_command_s", round(restored - on_began, 1))
        board.reconnect()
        new_boot_id = board.run(_BOOT_ID_CMD, check=True)[0][0]
        assert new_boot_id != old_boot_id, (
            "the board answered in the same boot: the power cut did not land"
        )
        return restored

    return cut
