"""Target-suite setup: switch on the shared board setup for every test here."""

import contextlib
import subprocess
import time
from datetime import datetime, timezone

import pytest

from panel import Panel
from replay import CA_PATH, CARDS4_LIVE

_CONFIG_PATH = "/data/config/config.json"
_CONFIG_COPY_PATH = "/tmp/kiosk-config.json"
_BROWSER_WAIT_SECONDS = 90
_BROWSER_POLL_SECONDS = 2
_HASHED_PATHS = (
    "/data/config/config.json",
    "/data/config/kiosk.conf",
    "/boot/config.txt",
    "/boot/cmdline.txt",
)
_CA_BOARD_PATH = "/tmp/replay-ca.pem"
_DROP_IN_PATH = "/run/systemd/system/wisekiosk.service.d/replay.conf"


def pytest_addoption(parser):
    parser.addoption("--soak", action="store_true", default=False, help="run the soak-marked tests")


def pytest_configure(config):
    config.addinivalue_line("markers", "soak: runs for hours; skipped unless --soak is given")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--soak"):
        return
    skip = pytest.mark.skip(
        reason="runs by hand: bench test <ref> -- --soak -k test_memory_over_a_long_run"
    )
    for item in items:
        if "soak" in item.keywords:
            item.add_marker(skip)


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
def replay_window(board, proxy, set_config, request):
    """Put the backend behind `proxy` for this test's duration, and return the browser start.

    Opens an `ssh -R` tunnel to the proxy's own loopback port, copies the proxy's CA to the
    board, writes a drop-in that points wisekiosk.service at the proxy through `HTTPS_PROXY`
    and adds the proxy's CA to its trust through `SSL_CERT_FILE`, then hands `set_config` the
    set's config.json -- whose own backend restart puts the backend onto the proxy before the
    browser starts. Teardown undoes each of this fixture's own steps in exactly the reverse
    order, then set_config's, then proxy's.

    Args:
        board (Board): the board under test (tests/conftest.py).
        proxy (wisebench.proxy.Proxy): the running proxy this test replays through.
        set_config (Callable[[str | os.PathLike], None]): swaps the board onto a config file.
        request (pytest.FixtureRequest): registers each step's undo.

    Returns:
        float: `time.monotonic()` taken once `set_config`'s `apply` has returned from starting
        `kiosk.service` -- the browser's start.
    """

    stack = contextlib.ExitStack()
    request.addfinalizer(stack.close)
    stack.enter_context(board.forward_remote_port(proxy.port, proxy.port))

    board.put(str(CA_PATH), _CA_BOARD_PATH)

    def _remove_ca():
        stdout, stderr, returncode = board.run(f"rm -f {_CA_BOARD_PATH}", timeout=None)
        output = stdout + stderr
        assert returncode == 0, (
            f"could not remove the replay CA (rc {returncode}): {chr(10).join(output)}"
        )

    request.addfinalizer(_remove_ca)

    stdout, stderr, returncode = board.run(
        "mkdir -p /run/systemd/system/wisekiosk.service.d && "
        f"printf '[Service]\\nEnvironment=HTTPS_PROXY=http://127.0.0.1:{proxy.port}\\n"
        f"Environment=SSL_CERT_FILE={_CA_BOARD_PATH}\\n' > {_DROP_IN_PATH} && "
        "systemctl daemon-reload",
        timeout=None,
    )
    output = stdout + stderr
    assert returncode == 0, (
        f"could not write the replay drop-in (rc {returncode}): {chr(10).join(output)}"
    )

    def _remove_drop_in():
        stdout, stderr, returncode = board.run(
            f"rm -f {_DROP_IN_PATH} && systemctl daemon-reload", timeout=None
        )
        output = stdout + stderr
        assert returncode == 0, (
            f"could not remove the replay drop-in (rc {returncode}): {chr(10).join(output)}"
        )

    request.addfinalizer(_remove_drop_in)

    set_config(CARDS4_LIVE / "config.json")
    return time.monotonic()


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
