"""Target-suite setup: the start-of-run install, the shared builds, the device context, and the Board hooks."""

import contextlib
from collections.abc import Callable, Iterator
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
from refused_offers import RefusedOffers

_BROWSER_WAIT_SECONDS = 90
_BROWSER_POLL_SECONDS = 2
_HASHED_PATHS = (
    "/data/config/kiosk.conf",
    "/boot/config.txt",
    "/boot/cmdline.txt",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add `--soak`, which runs TST014 with its long period.

    Args:
        parser: pytest's option parser.
    """
    parser.addoption("--soak", action="store_true", default=False, help="run TST014 with its long period")


@pytest.fixture(scope="session")
def config_hashes_across_install(
    request: pytest.FixtureRequest, target: Target, bench_candidate: str | None
) -> ConfigHashes | None:
    """Hash the board's config before and after `install_candidate`, through a board of its own; writes nothing.

    First clears what a dead run can leave in `/run`: a bind mount over the live config path, the
    backend's runtime drop-ins and a runtime mask on it.

    Args:
        request: runs `install_candidate` between the two hashes.
        target: the board's labgrid target.
        bench_candidate: the commit under test, or None outside a build.

    Returns:
        The sha256 of the live config before the install, after it, and of the image default after it
        (each None if the file is missing); None when there is no candidate to install.
    """
    with Board(target) as board:
        config = board.app.config
        config.unmount_stale_bind()
        board.app.backend.clear_runtime_overrides()
        if bench_candidate is None:
            request.getfixturevalue("install_candidate")
            return None
        before = config.live_sha256()
        request.getfixturevalue("install_candidate")
        return ConfigHashes(before, config.live_sha256(), config.default_sha256())


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(config_hashes_across_install: ConfigHashes | None) -> None:
    """Activate `install_candidate` (tests/conftest.py) for every test here, via `config_hashes_across_install`.

    Args:
        config_hashes_across_install: the config's hashes across the start-of-run install.
    """


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


def pytest_configure(config: pytest.Config) -> None:
    """Register the `sends_update` marker.

    Args:
        config: the run's config.
    """
    config.addinivalue_line("markers", "sends_update: the test sends an image update after the start-of-run install")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run the tests marked `sends_update` last, each group in collection order.

    Args:
        items: the collected tests, sorted in place.
    """
    items[:] = sorted(items, key=lambda item: item.get_closest_marker("sends_update") is not None)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Iterator[None]:
    """Put a new Board and the test's Record on a BoardTest, before its setup_method runs.

    Args:
        item: the test about to be set up.

    Returns:
        What pytest's own setup returns, once it has run the fixtures and `setup_method`.
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


def _utc_now() -> str:
    """The time now, in UTC.

    Returns:
        The time, in ISO 8601.
    """
    return datetime.now(UTC).isoformat()


def _browser_pid(board: Board) -> str:
    """Wait for the browser, which starts some seconds after ssh does following a restart.

    Args:
        board: the board under test.

    Returns:
        The browser's pid.
    """

    def surf_pid() -> str | None:
        """Read the browser's pid.

        Returns:
            The pid, or None if the browser is not running.
        """
        pgrep = board.run("pgrep -x surf")
        return pgrep.lines[0].strip() if pgrep.returncode == 0 and pgrep.lines else None

    found_s, pid = board.poll(surf_pid, until=bool, within=_BROWSER_WAIT_SECONDS, every=_BROWSER_POLL_SECONDS)
    assert found_s is not None, "the browser never appeared"
    return pid


@pytest.fixture(autouse=True)
def device_context(target: Target, record_property: Callable[[str, object], None]) -> Iterator[None]:
    """Record the board as the test found it, through a board of its own, and the end time after the test.

    Facts are raw board output: a missing file is simply absent from `file_sha256`.

    Args:
        target: the board's labgrid target.
        record_property: records each fact.

    Yields:
        None: the test runs, then `end` is recorded.
    """
    with Board(target) as board:
        pid = _browser_pid(board)
        hashed = " ".join((board.app.config.LIVE_PATH, *_HASHED_PATHS))
        sums = board.run("sha256sum " + hashed)
        assert sums.returncode in (0, 1), f"sha256sum failed (rc {sums.returncode}): {chr(10).join(sums.stderr)}"
        environ = board.run(f"tr '\\0' '\\n' < /proc/{pid}/environ", check=True).text.splitlines()
        xrandr = board.run("DISPLAY=:0 xrandr", check=True).text.splitlines()
        facts = {
            "boot_id": board.run(Board.BOOT_ID_CMD, check=True).text,
            "uptime_s": float(board.run("cat /proc/uptime", check=True).text.split()[0]),
            "kernel": board.run("uname -r", check=True).text,
            "file_sha256": "\n".join(sums.lines),
            "browser_cmdline_sha256": board.run(f"sha256sum /proc/{pid}/cmdline", check=True).text.split()[0],
            "browser_webkit_env": ",".join(line for line in environ if line.startswith("WEBKIT_")),
            "display_mode": next((line.strip() for line in xrandr if "*" in line), ""),
            "timesync": board.run("timedatectl show -p NTPSynchronized --value", check=True).text,
            "start": _utc_now(),
        }
    for key, value in facts.items():
        record_property(key, value)
    yield
    record_property("end", _utc_now())
