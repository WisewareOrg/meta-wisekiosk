"""Target-suite setup: the start-of-run install, the shared builds, the device context, and the Board hooks."""

import contextlib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from board import Board
from board.updates import Installed
from board_test import BoardTest
from candidate_bundles import CandidateBundles
from evemu_helpers import EvemuHelpers
from labgrid import Target
from record import Record
from refused_offers import RefusedOffers

_HASHED_PATHS = (
    "/data/config/kiosk.conf",
    "/boot/config.txt",
    "/boot/cmdline.txt",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add `--soak`, which also runs the tests marked `soak`.

    Args:
        parser: pytest's option parser.
    """
    parser.addoption("--soak", action="store_true", default=False, help="also run TST014 over its day-long soak")


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(install_candidate: Installed | None) -> None:
    """Activate `install_candidate` (tests/conftest.py) for every test here.

    Args:
        install_candidate: the start-of-run install.
    """


@pytest.fixture(scope="session")
def candidate_bundles(bench_candidate: str | None) -> Iterator[CandidateBundles]:
    """Build the image-update tests' bundles once per run; skips the tests outside a build.

    Args:
        bench_candidate: the commit under test, or None outside a build.

    Yields:
        CandidateBundles: the bundles, whose run directory is removed once the run ends.
    """
    with contextlib.ExitStack() as cleanup:
        yield CandidateBundles.build(cleanup, bench_candidate)


@pytest.fixture(autouse=True)
def _board_and_record(
    request: pytest.FixtureRequest, target: Target, record_property: Callable[[str, object], None]
) -> None:
    """Put a new Board, which reaches the run's fixtures on demand, and the test's Record on a BoardTest.

    It runs before the class's `setup_method`.

    Args:
        request: the test's request; the Board reaches the run's fixtures through it.
        target: the board's labgrid target.
        record_property: writes one property of the test's record.
    """
    if isinstance(request.instance, BoardTest):
        request.instance.board = Board(target, fixtures=request.getfixturevalue)
        request.instance.record = Record(record_property)


@pytest.fixture(scope="module")
def refused_offers(target: Target) -> Iterator[RefusedOffers]:
    """Build the refused-update tests' bundles once per module, for the `compatible` the board reports.

    Args:
        target: the board's labgrid target; the compatible is read through a board of its own.

    Yields:
        RefusedOffers: the bundles, whose work directory is removed once the module ends.
    """
    with Board(target) as board:
        compatible = board.updates.rauc_status()["compatible"]
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
    """Register the `sends_update` and `soak` markers.

    Args:
        config: the run's config.
    """
    config.addinivalue_line("markers", "sends_update: the test sends an image update after the start-of-run install")
    config.addinivalue_line("markers", "soak: a long run on top of the suite, run only under `--soak`")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deselect the tests marked `soak` unless `--soak` is given; run the tests marked `sends_update` last.

    Args:
        config: the run's config.
        items: the collected tests, filtered and sorted in place.
    """
    soaks = [] if config.getoption("--soak") else [item for item in items if item.get_closest_marker("soak")]
    if soaks:
        config.hook.pytest_deselected(items=soaks)
    kept = [item for item in items if item not in soaks]
    items[:] = sorted(kept, key=lambda item: item.get_closest_marker("sends_update") is not None)


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
        # the browser starts some seconds after ssh does following a restart
        board.seconds_until(board.app.browser.is_running)
        pid = board.run("pgrep -x surf", check=True).text.partition("\n")[0]
        hashed = " ".join((board.app.config.LIVE_PATH, *_HASHED_PATHS))
        sums = board.run("sha256sum " + hashed)
        assert sums.returncode in (0, 1), f"sha256sum failed (rc {sums.returncode}): {chr(10).join(sums.stderr)}"
        environ = board.run(f"tr '\\0' '\\n' < /proc/{pid}/environ", check=True).text.splitlines()
        xrandr = board.run("DISPLAY=:0 xrandr", check=True).text.splitlines()
        facts = {
            "boot_id": board.boot_id(),
            "uptime_s": board.uptime_s(),
            "kernel": board.run("uname -r", check=True).text,
            "file_sha256": "\n".join(sums.stdout),
            "browser_cmdline_sha256": board.run(f"sha256sum /proc/{pid}/cmdline", check=True).text.split()[0],
            "browser_webkit_env": ",".join(line for line in environ if line.startswith("WEBKIT_")),
            "display_mode": next((line.strip() for line in xrandr if "*" in line), ""),
            "timesync": board.run("timedatectl show -p NTPSynchronized --value", check=True).text,
            "start": datetime.now(UTC).isoformat(),
        }
    for key, value in facts.items():
        record_property(key, value)
    yield
    record_property("end", datetime.now(UTC).isoformat())
