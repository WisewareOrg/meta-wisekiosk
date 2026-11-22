"""Target-suite setup: switch on the shared board setup for every test here."""

import contextlib
import subprocess
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from board import Board
from board.app.config import ConfigHashes
from board_test import BoardTest
from candidate_bundles import CandidateBundles
from evemu_helpers import EvemuHelpers
from labgrid import Target
from labgrid.pytestplugin.hooks import LABGRID_ENV_KEY
from record import Record
from recovery import BACKEND_DROP_IN_DIR, RELOAD_TIMEOUT_SECONDS
from refused_offers import RefusedOffers

_BROWSER_WAIT_SECONDS = 90
_BROWSER_POLL_SECONDS = 2
_HASHED_PATHS = (
    "/data/config/kiosk.conf",
    "/boot/config.txt",
    "/boot/cmdline.txt",
)
_BACKEND_SWEEP = (
    f"if [ -d {BACKEND_DROP_IN_DIR} ] || "
    '[ "$(systemctl is-enabled wisekiosk.service)" = masked-runtime ]; then '
    f"rm -rf {BACKEND_DROP_IN_DIR}; systemctl unmask --runtime wisekiosk.service; "
    "systemctl daemon-reload; systemctl start wisekiosk.service; fi"
)


def pytest_addoption(parser):
    """Add `--soak`, which runs TST014 with its long period."""
    parser.addoption("--soak", action="store_true", default=False, help="run TST014 with its long period")


@pytest.fixture(scope="session")
def config_hashes_across_install(request, board, bench_candidate):
    """Hash the board's config before and after `install_candidate`; writes nothing.

    First clears what a dead run can leave in `/run`: a bind mount over the live config path, the
    backend's runtime drop-ins and a runtime mask on it.

    Args:
        request (pytest.FixtureRequest): runs `install_candidate` between the two hashes.
        board (Board): the board under test (tests/conftest.py).
        bench_candidate (str | None): the commit under test, or None outside a build.

    Returns:
        ConfigHashes | None: the sha256 of the live config before the install, after it, and of the
            image default after it (each None if the file is missing); None when there is no
            candidate to install.
    """
    board.unmount_if_mounted(board.CONFIG_PATH)
    board.run(_BACKEND_SWEEP, check=True, timeout=RELOAD_TIMEOUT_SECONDS)
    if bench_candidate is None:
        request.getfixturevalue("install_candidate")
        return None
    before = board.sha256(board.CONFIG_PATH)
    request.getfixturevalue("install_candidate")
    return ConfigHashes(before, board.sha256(board.CONFIG_PATH), board.sha256(board.DEFAULT_CONFIG_PATH))


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(config_hashes_across_install):
    """Activate `install_candidate` (tests/conftest.py) for every test here, via `config_hashes_across_install`."""


@pytest.fixture(scope="module")
def candidate_bundles(bench_candidate: str | None) -> Iterator[CandidateBundles]:
    """Build the image-update tests' bundles once per module; skips the tests outside a build.

    Args:
        bench_candidate: the commit under test, or None outside a build.

    Yields:
        CandidateBundles: the bundles, whose run directory is removed once the module ends.
    """
    with contextlib.ExitStack() as cleanup:
        yield CandidateBundles.build(cleanup, bench_candidate)


@pytest.fixture(scope="module")
def refused_offers(target: Target) -> Iterator[RefusedOffers]:
    """Build the refused-update tests' bundles once per module, for the `compatible` the board reports.

    Args:
        target: the board's labgrid target; the compatible is read through a board of its own.

    Yields:
        RefusedOffers: the bundles, whose work directory is removed once the module ends.
    """
    with Board(target) as board:
        compatible = board.updates.compatible()
    with contextlib.ExitStack() as cleanup:
        yield RefusedOffers.build(cleanup, compatible)


@pytest.fixture(scope="module")
def evemu_helpers() -> Iterator[EvemuHelpers]:
    """Build evemu-tools and its library once per module, for TST027's keyboard.

    Yields:
        EvemuHelpers: the built files, whose work directory is removed once the module ends.
    """
    with contextlib.ExitStack() as cleanup:
        yield EvemuHelpers.build(cleanup)


def pytest_configure(config):
    """Register the `sends_update` marker."""
    config.addinivalue_line("markers", "sends_update: the test sends an image update after the start-of-run install")


def pytest_collection_modifyitems(items):
    """Run the tests marked `sends_update` last, each group in collection order."""
    items[:] = sorted(items, key=lambda item: item.get_closest_marker("sends_update") is not None)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Iterator[None]:
    """Put a new Board and the test's Record on a BoardTest, before its setup_method runs.

    Args:
        item: the test about to be set up.

    Yields:
        None: pytest's own setup runs, the fixtures and `setup_method` among it.
    """
    if isinstance(item.instance, BoardTest):
        env = item.config.stash[LABGRID_ENV_KEY]
        if env is None:
            pytest.skip("missing environment config (use --lg-env)")
        item.instance.board = Board(env.get_target())
        item.instance.record = Record(lambda name, value: item.user_properties.append((name, value)))
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> Iterator[None]:
    """Undo what the test changed on the board, last first, before the fixtures tear down.

    The undo runs in `try` and pytest's teardown in `finally`, so a failing undo is reported as a
    teardown error and the fixtures still tear down.

    Args:
        item: the test being torn down.
        nextitem: the test after it, which pytest's own teardown reads.

    Yields:
        None: pytest's own teardown runs, the fixtures' among it.
    """
    try:
        board = getattr(item.instance, "board", None)
        if board is not None:
            board.cleanup.close()
    finally:
        yield


def _utc_now():
    return datetime.now(UTC).isoformat()


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
