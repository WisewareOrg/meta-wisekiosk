"""Target-suite setup: the run's hooks, its start-of-run install and each test's device record.

Also the fixtures that set the board's state, observe the panel and inject faults.
"""

import contextlib
import subprocess
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from backend import Backend
from board import Board
from labgrid import Target
from outage import Outage
from panel import Panel
from replay import CA_PATH, CARDS4_LIVE

if TYPE_CHECKING:
    from wisebench.proxy import Proxy

_BROWSER_WAIT_SECONDS = 90
_BROWSER_POLL_SECONDS = 2
_HASHED_PATHS = (
    "/data/config/kiosk.conf",
    "/boot/config.txt",
    "/boot/cmdline.txt",
)
_CA_BOARD_PATH = "/tmp/replay-ca.pem"
_DROP_IN_PATH = f"{Backend.DROP_IN_DIR}/replay.conf"
_POWER_OFF_SECONDS = 10


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the `--soak` option.

    Args:
        parser: pytest's option parser.
    """
    parser.addoption("--soak", action="store_true", default=False, help="run TST014 with its long period")


def pytest_configure(config: pytest.Config) -> None:
    """Register the `sends_update` marker.

    Args:
        config: pytest's configuration.
    """
    config.addinivalue_line("markers", "sends_update: the test sends an image update after the start-of-run install")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run the tests marked `sends_update` last, each group in collection order.

    Args:
        items: the collected tests, reordered in place.
    """
    items[:] = sorted(items, key=lambda item: item.get_closest_marker("sends_update") is not None)


@pytest.fixture(scope="session")
def config_across_update(
    request: pytest.FixtureRequest, board: Board, bench_candidate: str | None
) -> tuple[str | None, str | None, str | None] | None:
    """Hash the board's config before and after `install_candidate`; writes nothing.

    First clears what a dead run can leave in `/run`: a bind mount over the live config path, the
    backend's runtime drop-ins and a runtime mask on it.

    Args:
        request: runs `install_candidate` between the two hashes.
        board: the board under test.
        bench_candidate: the commit under test, or None outside a build.

    Returns:
        The sha256 of the live config before the install, after it, and of the image default after
        it (each None if the file is missing); None when there is no candidate to install.

    Raises:
        AssertionError: clearing what a dead run left fails.
    """
    board.unmount_if_mounted(board.CONFIG_PATH)
    board.run(Backend.SWEEP, check=True, timeout=Backend.RELOAD_TIMEOUT_SECONDS)
    if bench_candidate is None:
        request.getfixturevalue("install_candidate")
        return None
    before = board.sha256(board.CONFIG_PATH)
    request.getfixturevalue("install_candidate")
    return before, board.sha256(board.CONFIG_PATH), board.sha256(board.DEFAULT_CONFIG_PATH)


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(config_across_update: tuple[str | None, str | None, str | None] | None) -> None:
    """Activate `install_candidate` (tests/conftest.py) for every test in this suite, via `config_across_update`.

    Args:
        config_across_update: runs `install_candidate` between its two hashes.
    """


@pytest.fixture(autouse=True)
def device_context(board: Board, record_property: Callable[[str, object], None]) -> Iterator[None]:
    """Record the board as the test found it, and the end time after the test.

    Facts are raw board output: a missing file is simply absent from `file_sha256`.

    Args:
        board: the board under test.
        record_property: records each fact and the end time.

    Yields:
        Nothing; the end time is recorded after the test.

    Raises:
        AssertionError: the browser never appeared, or a read of the board fails.
    """

    def surf_pid() -> str | None:
        """The browser's first pid, or None while it is not running.

        Returns:
            The pid, or None.
        """
        stdout, _stderr, returncode = board.run("pgrep -x surf")
        return stdout[0].strip() if returncode == 0 and stdout else None

    # the browser starts some seconds after ssh does following a restart
    appeared_s, pid = board.wait(surf_pid, bool, _BROWSER_WAIT_SECONDS, every=_BROWSER_POLL_SECONDS)
    assert appeared_s is not None, "the browser never appeared"

    hashed = " ".join((board.CONFIG_PATH, *_HASHED_PATHS))
    sums_out, sums_err, sums_rc = board.run("sha256sum " + hashed)
    assert sums_rc in (0, 1), f"sha256sum failed (rc {sums_rc}): {chr(10).join(sums_err)}"
    environ = board.read(f"tr '\\0' '\\n' < /proc/{pid}/environ").splitlines()
    xrandr = board.read("DISPLAY=:0 xrandr").splitlines()
    facts = {
        "boot_id": board.read(board.BOOT_ID_CMD),
        "uptime_s": float(board.read("cat /proc/uptime").split()[0]),
        "kernel": board.read("uname -r"),
        "file_sha256": "\n".join(sums_out),
        "browser_cmdline_sha256": board.read(f"sha256sum /proc/{pid}/cmdline").split()[0],
        "browser_webkit_env": ",".join(line for line in environ if line.startswith("WEBKIT_")),
        "display_mode": next((line.strip() for line in xrandr if "*" in line), ""),
        "timesync": board.read("timedatectl show -p NTPSynchronized --value"),
        "start": datetime.now(UTC).isoformat(),
    }
    for key, value in facts.items():
        record_property(key, value)
    yield
    record_property("end", datetime.now(UTC).isoformat())


@pytest.fixture
def backend(board: Board, request: pytest.FixtureRequest, record_property: Callable[[str, object], None]) -> Backend:
    """The `Backend` for the board; its changes are undone at this fixture's teardown.

    Args:
        board: the board under test.
        request: registers the backend's undos, which run after the test's own finalizers.
        record_property: records what the backend's kill measures.

    Returns:
        The backend, with nothing changed yet.
    """
    return Backend(board, request, record_property)


@pytest.fixture
def replay_window(board: Board, backend: Backend, proxy: "Proxy", request: pytest.FixtureRequest) -> float:
    """Put the backend behind `proxy` for this test's duration, and return the browser start.

    Opens an `ssh -R` tunnel to the proxy's own loopback port, copies the proxy's CA to the
    board, writes a drop-in that points wisekiosk.service at the proxy through `HTTPS_PROXY`
    and adds the proxy's CA to its trust through `SSL_CERT_FILE`, then hands `backend.use_config`
    the set's config.json -- whose own backend restart puts the backend onto the proxy before the
    browser starts. Teardown undoes each of this fixture's own steps in exactly the reverse
    order, then the backend's, then proxy's.

    Args:
        board: the board under test.
        backend: swaps the board onto the replay set's config and carries the drop-in.
        proxy: the running proxy this test replays through.
        request: registers each of this fixture's own undos.

    Returns:
        `time.monotonic()` taken once `backend.use_config` has returned from starting
        `kiosk.service` -- the browser's start.

    Raises:
        AssertionError: a step on the board fails.
    """
    stack = contextlib.ExitStack()
    request.addfinalizer(stack.close)
    stack.enter_context(board.forward_remote_port(proxy.port, proxy.port))

    board.put(str(CA_PATH), _CA_BOARD_PATH)
    request.addfinalizer(lambda: board.run(f"rm -f {_CA_BOARD_PATH}", check=True, timeout=None))

    backend.write_drop_in(
        "replay.conf",
        f"Environment=HTTPS_PROXY=http://127.0.0.1:{proxy.port}\nEnvironment=SSL_CERT_FILE={_CA_BOARD_PATH}",
    )
    request.addfinalizer(
        lambda: board.run(f"rm -f {_DROP_IN_PATH} && systemctl daemon-reload", check=True, timeout=None)
    )

    backend.use_config(CARDS4_LIVE / "config.json")
    return time.monotonic()


@pytest.fixture
def panel(board: Board, request: pytest.FixtureRequest, record_property: Callable[[str, object], None]) -> Panel:
    """Load the probe into the browser and return the `Panel`; the page wait is the test's.

    Args:
        board: the board under test.
        request: registers the probe's undos, which run at this fixture's teardown.
        record_property: records the probe's hash.

    Returns:
        The panel, with the probe installed.
    """
    observation = Panel(board, request, record_property)
    observation.install()
    return observation


@pytest.fixture
def outage(board: Board) -> Outage:
    """The `Outage` for the board; the test arms it.

    Args:
        board: the board under test.

    Returns:
        The outage, not yet armed.
    """
    return Outage(board)


@pytest.fixture
def power_cut(
    target: Target,
    board: Board,
    request: pytest.FixtureRequest,
    record_property: Callable[[str, object], None],
) -> Callable[[], float]:
    """A power cut through the bench's switched plug; power is switched back on at teardown.

    Args:
        target: names the bench's switched plug, the `ExternalPowerDriver`.
        board: the board under test.
        request: registers the switching back on.
        record_property: records `power_on_command_s`.

    Returns:
        The `cut()` the test calls. It cuts the board's power, restores it and reconnects once the
        board answers in a new boot, and returns the host `time.monotonic()` at which the `on`
        command started. Power returns no earlier, so a time taken from it errs high. It exits the
        run if the plug fails, or if the board answers in the same boot after the power was off.
    """
    power = target.get_driver("ExternalPowerDriver")
    request.addfinalizer(power.on)

    def cut() -> float:
        """Cut power, restore it, and reconnect in a new boot.

        Returns:
            The host `time.monotonic()` at which the `on` command started.
        """
        old_boot_id = board.read(board.BOOT_ID_CMD)
        board.disconnect()
        try:
            power.off()
            time.sleep(_POWER_OFF_SECONDS)
            on_began = time.monotonic()
            power.on()
        except (subprocess.CalledProcessError, OSError) as error:
            pytest.exit(f"the bench's power switch failed: {error}", returncode=2)
        record_property("power_on_command_s", round(time.monotonic() - on_began, 1))
        board.reconnect()
        if board.read(board.BOOT_ID_CMD) == old_boot_id:
            pytest.exit(
                f"the board answered in the same boot after {_POWER_OFF_SECONDS} s off: "
                "the plug or its supply did not cut power",
                returncode=2,
            )
        return on_began

    return cut
