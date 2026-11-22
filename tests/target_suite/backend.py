"""The WiseKiosk backend as a test drives it: its config, a held restart, a kill and a mask."""

import os
from collections.abc import Callable

import pytest
from board import Board


class Backend:
    """wisekiosk.service for one test: its config, its runtime drop-ins in `/run`, a kill and a mask.

    Each change registers its undo once it has taken, on the request the backend was built with.
    `kill` keeps the MainPID that `assert_kill_landed` compares against, and `SWEEP` clears what a
    dead run left in `/run`.

    Attributes:
        DROP_IN_DIR: where the runtime drop-ins of the service live.
        RELOAD_TIMEOUT_SECONDS: covers a daemon-reload plus a backend start.
        MAIN_PID_CMD: prints the service's MainPID as systemd reports it.
        SWEEP: the board command that removes the drop-ins and the runtime mask a dead run left.
    """

    DROP_IN_DIR = "/run/systemd/system/wisekiosk.service.d"
    RELOAD_TIMEOUT_SECONDS = 60
    MAIN_PID_CMD = "systemctl show -p MainPID --value wisekiosk.service"
    SWEEP = (
        f"if [ -d {DROP_IN_DIR} ] || "
        '[ "$(systemctl is-enabled wisekiosk.service)" = masked-runtime ]; then '
        f"rm -rf {DROP_IN_DIR}; systemctl unmask --runtime wisekiosk.service; "
        "systemctl daemon-reload; systemctl start wisekiosk.service; fi"
    )
    _RELEASE = "systemctl unmask --runtime wisekiosk.service; systemctl start wisekiosk.service"
    _RELEASE_UNIT = "test-backend-release"

    def __init__(
        self, board: Board, request: pytest.FixtureRequest, record_property: Callable[[str, object], None]
    ) -> None:
        """Bind to the board, and to the request whose teardown undoes each change.

        Args:
            board: the board under test.
            request: registers each change's undo.
            record_property: records what `kill` and `assert_kill_landed` measure.
        """
        self._board = board
        self._request = request
        self._record_property = record_property
        # the MainPID `kill` took down
        self._killed_pid: str | None = None

    def use_config(self, path: str | os.PathLike[str]) -> None:
        """Swap the board onto `path`'s config and leave the instance running against it.

        Stops the browser, bind-mounts a copy of `path` over the live config, restarts the backend and
        waits for the page, then starts the browser. Each step's undo is registered once that step
        has succeeded, so teardown runs them in reverse even if a later step fails -- except the
        backend restart's undo, registered right after the restart itself succeeds and before the
        page wait, so it still runs if that wait fails. Call it at most once per test.

        Args:
            path: the config file on the host.
        """
        board = self._board
        board.run("systemctl stop kiosk.service", check=True)
        self._request.addfinalizer(lambda: board.run("systemctl start kiosk.service", check=True))
        board.bind(self._request, path, board.CONFIG_PATH)
        board.run("systemctl restart wisekiosk.service", check=True)
        self._request.addfinalizer(self._restart_and_wait)
        board.wait_for_page()
        board.run("systemctl start kiosk.service", check=True)
        self._request.addfinalizer(lambda: board.run("systemctl stop kiosk.service", check=True))

    def write_drop_in(self, name: str, body: str) -> None:
        """Write the runtime drop-in `name` with `body` as its `[Service]` section and reload systemd.

        It registers no undo.

        Args:
            name: the drop-in's file name.
            body: the `[Service]` lines, one per line.
        """
        text = "\\n".join(["[Service]", *body.splitlines()])
        self._board.run(
            f"mkdir -p {self.DROP_IN_DIR} && printf '{text}\\n' > {self.DROP_IN_DIR}/{name} && systemctl daemon-reload",
            check=True,
            timeout=self.RELOAD_TIMEOUT_SECONDS,
        )

    def hold(self, seconds: int) -> None:
        """Delay the backend's own restart to `seconds` with a runtime drop-in, until `unhold`.

        Args:
            seconds: the `RestartSec` to hold it to.
        """
        self._request.addfinalizer(self.unhold)
        self.write_drop_in("hold.conf", f"RestartSec={seconds}")

    def unhold(self) -> None:
        """Remove the hold, start the backend and wait for the page; idempotent.

        A caller may register it again to run earlier at teardown.
        """
        self._board.run(
            f"rm -f {self.DROP_IN_DIR}/hold.conf; systemctl daemon-reload; systemctl start wisekiosk.service",
            check=True,
            timeout=self.RELOAD_TIMEOUT_SECONDS,
        )
        self._board.wait_for_page()

    def kill(self) -> float:
        """SIGKILL the backend, keeping its MainPID, and record `killed_at_uptime_s` and `main_pid_before`.

        Returns:
            The board's uptime at the kill.
        """
        self._killed_pid = self.main_pid()
        killed_at = self._board.timed("systemctl kill --signal=KILL wisekiosk.service", check=True)[0]
        self._record_property("killed_at_uptime_s", killed_at)
        self._record_property("main_pid_before", self._killed_pid)
        return killed_at

    def assert_kill_landed(self) -> None:
        """Assert the backend answering after the kill is a new process, and record `main_pid_after`.

        Raises:
            RuntimeError: `kill` has not run.
        """
        if self._killed_pid is None:
            raise RuntimeError("assert_kill_landed needs kill to have run")
        new_pid = self.main_pid()
        self._record_property("main_pid_after", new_pid)
        assert new_pid != self._killed_pid, (
            f"INVALID CHECK, not an appliance failure: the kill did not land (MainPID {self._killed_pid} unchanged)"
        )

    def main_pid(self) -> str:
        """The backend's MainPID as systemd reports it.

        Returns:
            The MainPID.
        """
        return self._board.read(self.MAIN_PID_CMD)

    def mask(self) -> None:
        """Mask the backend for this boot only, until `unmask`."""
        self._request.addfinalizer(self.unmask)
        self._board.run("systemctl mask --runtime wisekiosk.service", check=True)

    def release(self) -> None:
        """Unmask and start the backend, without waiting for the page."""
        self._board.run(self._RELEASE, check=True)

    def unmask(self) -> None:
        """Release the backend, then wait for the page; idempotent.

        A caller may register it again to run earlier at teardown.
        """
        self.release()
        self._board.wait_for_page()

    def release_after(self, seconds: float) -> None:
        """Have a board-side timer release the backend in `seconds`, whatever the host does.

        Args:
            seconds: the delay of the timer.
        """
        self._board.run_later(self._request, self._RELEASE_UNIT, seconds, f"/bin/sh -c '{self._RELEASE}'")

    def _restart_and_wait(self) -> None:
        """Restart the backend and wait for the page."""
        self._board.run("systemctl restart wisekiosk.service", check=True)
        self._board.wait_for_page()
