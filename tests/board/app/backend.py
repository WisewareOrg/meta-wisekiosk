"""wisekiosk.service, the WiseKiosk app's backend."""

import contextlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wisebench.proxy import Proxy

    from board import Board

# the CA the replay proxy signs its answers with, as mitmproxy writes it on the test host
_PROXY_CA_PATH = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
_PROXY_CA_BOARD_PATH = "/tmp/replay-ca.pem"


class Backend:
    """wisekiosk.service on the board: its process, a delay on its own restart, and its mask.

    Each change registers its undo on the board's cleanup once it has taken.
    """

    _DROP_IN_DIR = "/run/systemd/system/wisekiosk.service.d"
    _DELAY_DROP_IN = f"{_DROP_IN_DIR}/hold.conf"
    _PROXY_DROP_IN = f"{_DROP_IN_DIR}/replay.conf"
    # covers a daemon-reload plus a backend start
    _RELOAD_TIMEOUT_SECONDS = 60
    _RUNTIME_OVERRIDES_SWEEP = (
        f"if [ -d {_DROP_IN_DIR} ] || "
        '[ "$(systemctl is-enabled wisekiosk.service)" = masked-runtime ]; then '
        f"rm -rf {_DROP_IN_DIR}; systemctl unmask --runtime wisekiosk.service; "
        "systemctl daemon-reload; systemctl start wisekiosk.service; fi"
    )
    _RELEASE = "systemctl unmask --runtime wisekiosk.service; systemctl start wisekiosk.service"
    _RELEASE_UNIT = "test-backend-release"

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board

    def clear_runtime_overrides(self) -> None:
        """Remove the runtime drop-ins and the runtime mask a dead run left on the backend, and start it."""
        self._board.run(self._RUNTIME_OVERRIDES_SWEEP, check=True, timeout=self._RELOAD_TIMEOUT_SECONDS)

    def pid(self) -> str:
        """Read the backend's MainPID as systemd reports it, retrying through a dropped session.

        Returns:
            The MainPID.
        """
        return self._board.run(
            "systemctl show -p MainPID --value wisekiosk.service", check=True, retry_for=self._board.READ_RETRY_SECONDS
        ).text

    def sigkill(self) -> float:
        """SIGKILL the backend.

        Returns:
            The board's uptime at the kill.
        """
        return self._board.run("systemctl kill --signal=KILL wisekiosk.service", check=True, with_uptime=True).uptime_s

    def assert_new_process_after_kill(self, pid_before: str) -> str:
        """Assert the backend answering after a kill is a new process; INVALID if it is not.

        Args:
            pid_before: the MainPID the kill was aimed at.

        Returns:
            The new MainPID.
        """
        pid_after = self.pid()
        assert pid_after != pid_before, (
            f"INVALID CHECK, not an appliance failure: the kill did not land (MainPID {pid_before} unchanged)"
        )
        return pid_after

    def delay_restart(self, seconds: int) -> None:
        """Delay the backend's own restart to `seconds` with a runtime drop-in, until `undo_restart_delay`.

        The undo is registered on the board's cleanup before the drop-in is written.

        Args:
            seconds: the `RestartSec` to delay it to.
        """
        self._board.cleanup.callback(self.undo_restart_delay)
        self._board.run(
            f"mkdir -p {self._DROP_IN_DIR} && printf '[Service]\\nRestartSec={seconds}\\n' > {self._DELAY_DROP_IN} && "
            "systemctl daemon-reload",
            check=True,
            timeout=self._RELOAD_TIMEOUT_SECONDS,
        )

    def undo_restart_delay(self) -> None:
        """Remove the restart delay, start the backend and wait for the page; safe to run twice."""
        self._board.run(
            f"rm -f {self._DELAY_DROP_IN}; systemctl daemon-reload; systemctl start wisekiosk.service",
            check=True,
            timeout=self._RELOAD_TIMEOUT_SECONDS,
        )
        self._board.wait_for_page()

    def put_behind(self, proxy: "Proxy", config: str | os.PathLike[str]) -> None:
        """Put the backend behind `proxy`, running the replay set's `config`, until the test ends.

        Opens an `ssh -R` tunnel to the proxy's own loopback port, copies the proxy's CA to the board,
        and writes a drop-in that points wisekiosk.service at the proxy through `HTTPS_PROXY` and adds
        the CA to its trust through `SSL_CERT_FILE`. The app then takes `config` through
        `board.app.config.use`, whose backend restart puts the backend onto the proxy before the
        browser starts. When the test ends the tunnel's steps are undone first, last first, then the
        config's, so the backend never runs behind a proxy that has gone.

        Args:
            proxy: the running proxy the backend replays through.
            config: the replay set's config file on the host.
        """
        board = self._board
        tunnel = contextlib.ExitStack()
        try:
            tunnel.enter_context(board.forward_remote_port(proxy.port, proxy.port))
            board.put(str(_PROXY_CA_PATH), _PROXY_CA_BOARD_PATH)
            tunnel.callback(board.run, f"rm -f {_PROXY_CA_BOARD_PATH}", check=True, timeout=None)
            board.run(
                f"mkdir -p {self._DROP_IN_DIR} && "
                f"printf '[Service]\\nEnvironment=HTTPS_PROXY=http://127.0.0.1:{proxy.port}\\n"
                f"Environment=SSL_CERT_FILE={_PROXY_CA_BOARD_PATH}\\n' > {self._PROXY_DROP_IN} && "
                "systemctl daemon-reload",
                check=True,
                timeout=None,
            )
            tunnel.callback(
                board.run, f"rm -f {self._PROXY_DROP_IN} && systemctl daemon-reload", check=True, timeout=None
            )
            board.app.config.use(config)
        finally:
            board.cleanup.push(tunnel)

    def mask(self) -> None:
        """Mask the backend for this boot only; when the test ends it is unmasked and started."""
        self._board.cleanup.callback(self.unmask_and_wait_for_page)
        self._board.run("systemctl mask --runtime wisekiosk.service", check=True)

    def unit_state(self) -> tuple[list[str], list[str]]:
        """What systemd says of the backend's unit.

        Returns:
            The stdout lines of `systemctl is-enabled` and of `systemctl is-active` for it.
        """
        enabled = self._board.run("systemctl is-enabled wisekiosk.service").lines
        active = self._board.run("systemctl is-active wisekiosk.service").lines
        return enabled, active

    def unmask_and_start(self) -> None:
        """Unmask and start the backend, without waiting for the page."""
        self._board.run(self._RELEASE, check=True)

    def unmask_and_wait_for_page(self) -> None:
        """Unmask and start the backend, then wait for the page; safe to run twice."""
        self.unmask_and_start()
        self._board.wait_for_page()

    def unmask_and_start_after(self, seconds: float) -> None:
        """Have a board-side timer unmask and start the backend in `seconds`, whatever the host does.

        Args:
            seconds: the timer's delay.
        """
        self._board.run_later(self._RELEASE_UNIT, seconds, f"/bin/sh -c '{self._RELEASE}'")
