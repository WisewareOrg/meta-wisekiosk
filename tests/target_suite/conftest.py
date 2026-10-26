"""Target-suite setup: get the board onto `bench_candidate`, then print its commit."""

import subprocess

import pytest

from page import POLL_ATTEMPT_TIMEOUT_SECONDS, poll_for_page

_CONFIG_PATH = "/data/config/config.json"
_CONFIG_COPY_PATH = "/tmp/kiosk-config.json"


@pytest.fixture(scope="session", autouse=True)
def install_candidate(target, bench_candidate):
    """Install `bench_candidate` on the board, if there is one, then print its commit.

    Installs by running `just kiosk-ota` and `just kiosk-reboot` against the board the
    target's NetworkService names. Either way, gets the SSHDriver, reads
    /etc/buildinfo, and prints the board's meta-wisekiosk commit as
    `board_commit=<sha>`.

    Args:
        target (labgrid.Target): names the board's NetworkService and SSHDriver.
        bench_candidate (str | None): the commit under test, or None outside a build.

    Raises:
        subprocess.CalledProcessError: `just kiosk-ota` or `just kiosk-reboot` exits
            nonzero.
        Exception: the SSHDriver's own activation times out reaching the board.
        AssertionError: /etc/buildinfo cannot be read, or carries no meta-wisekiosk
            line.
    """
    if bench_candidate is not None:
        service = target.get_resource("NetworkService")
        host = f"{service.username}@{service.address}"
        subprocess.run(["just", "kiosk-ota", host], check=True)
        subprocess.run(["just", "kiosk-reboot", host], check=True)
    driver = target.get_driver("SSHDriver")
    stdout, _stderr, returncode = driver.run("cat /etc/buildinfo")
    assert returncode == 0, "could not read /etc/buildinfo on the board"
    line = next(
        (entry for entry in stdout if entry.split()[:2] == ["meta-wisekiosk", "="]),
        None,
    )
    assert line is not None, f"no meta-wisekiosk layer line in buildinfo:\n{chr(10).join(stdout)}"
    board_commit = line.split()[2].rsplit(":", 1)[-1]
    print(f"board_commit={board_commit}")


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
    Call it at most once per test.

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
