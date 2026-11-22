"""The WiseKiosk backend as a test drives it: its MainPID, a kill, and a restart held back by a runtime drop-in."""

BACKEND_DROP_IN_DIR = "/run/systemd/system/wisekiosk.service.d"
# covers a daemon-reload plus a backend start
RELOAD_TIMEOUT_SECONDS = 60
_HOLD_PATH = f"{BACKEND_DROP_IN_DIR}/hold.conf"
MAIN_PID_CMD = "systemctl show -p MainPID --value wisekiosk.service"


def hold_restart(board, request, seconds):
    """Delay the backend's own restart to `seconds` with a runtime drop-in; undo it at teardown.

    Returns:
        Callable[[], None]: the undo -- remove the drop-in, start the backend and wait for the
            page; idempotent, so a caller may register it again to run earlier at teardown.
    """

    def unhold():
        board.run(
            f"rm -f {_HOLD_PATH}; systemctl daemon-reload; systemctl start wisekiosk.service",
            check=True,
            timeout=RELOAD_TIMEOUT_SECONDS,
        )
        assert board.wait_for_page(), "the page did not serve after the restart hold was removed"

    request.addfinalizer(unhold)
    board.run(
        f"mkdir -p {BACKEND_DROP_IN_DIR} && printf '[Service]\\nRestartSec={seconds}\\n' > {_HOLD_PATH} && "
        "systemctl daemon-reload",
        check=True,
        timeout=RELOAD_TIMEOUT_SECONDS,
    )
    return unhold


def main_pid(board):
    """The backend's MainPID as systemd reports it."""
    return board.run(MAIN_PID_CMD, check=True)[0][0].strip()


def kill_backend(board):
    """SIGKILL the backend; return the board uptime of the kill and the MainPID before it."""
    old_pid = main_pid(board)
    stdout, _stderr, _returncode = board.run(
        "cat /proc/uptime; systemctl kill --signal=KILL wisekiosk.service", check=True
    )
    return float(stdout[0].split()[0]), old_pid


def assert_kill_landed(board, old_pid):
    """Assert the backend answering after the kill is a new process; return its MainPID."""
    new_pid = main_pid(board)
    assert new_pid != old_pid, (
        f"INVALID CHECK, not an appliance failure: the kill did not land (MainPID {old_pid} unchanged)"
    )
    return new_pid
