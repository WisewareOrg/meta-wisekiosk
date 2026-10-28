"""Target-suite setup: switch on the shared board setup for every test here."""

import pytest

from page import POLL_ATTEMPT_TIMEOUT_SECONDS, poll_for_page

_CONFIG_PATH = "/data/config/config.json"
_CONFIG_COPY_PATH = "/tmp/kiosk-config.json"


@pytest.fixture(scope="session", autouse=True)
def _install_candidate(install_candidate):
    """Activate `install_candidate` (tests/conftest.py) for every test in this suite."""


def _run_checked(driver, cmd):
    """Run `cmd` on the board and assert it returned 0.

    Args:
        driver (labgrid.driver.SSHDriver): the board's remote shell.
        cmd (str): the command to run.

    Returns:
        list[str]: `cmd`'s combined stdout and stderr lines.

    Raises:
        AssertionError: `cmd` returned nonzero.
    """
    stdout, stderr, returncode = driver.run(cmd, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
    output = stdout + stderr
    assert returncode == 0, f"{cmd!r} failed (rc {returncode}): {chr(10).join(output)}"
    return output


@pytest.fixture
def set_config(target, request):
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
        target (labgrid.Target): names the board's SSHDriver.
        request (pytest.FixtureRequest): registers each step's undo.

    Returns:
        Callable[[str | os.PathLike], None]: `apply(path)`.
    """
    driver = target.get_driver("SSHDriver")

    def apply(path):
        """Swap the board onto `path`'s config and leave the instance running against it.

        Args:
            path (str | os.PathLike): the config file to copy to the board.
        """
        _run_checked(driver, "systemctl stop kiosk.service")
        request.addfinalizer(lambda: _run_checked(driver, "systemctl start kiosk.service"))

        _run_checked(
            driver,
            f"if grep -q ' {_CONFIG_PATH} ' /proc/self/mountinfo; then umount {_CONFIG_PATH}; fi",
        )

        driver.put(str(path), _CONFIG_COPY_PATH)
        request.addfinalizer(lambda: _run_checked(driver, f"rm -f {_CONFIG_COPY_PATH}"))

        _run_checked(driver, f"mount --bind {_CONFIG_COPY_PATH} {_CONFIG_PATH}")
        request.addfinalizer(lambda: _run_checked(driver, f"umount {_CONFIG_PATH}"))

        def _restart_backend_and_wait():
            _run_checked(driver, "systemctl restart wisekiosk.service")
            assert poll_for_page(driver), "page did not serve after the backend restart"

        _run_checked(driver, "systemctl restart wisekiosk.service")
        request.addfinalizer(_restart_backend_and_wait)
        assert poll_for_page(driver), "page did not serve after the backend restart"

        _run_checked(driver, "systemctl start kiosk.service")
        request.addfinalizer(lambda: _run_checked(driver, "systemctl stop kiosk.service"))

    return apply
