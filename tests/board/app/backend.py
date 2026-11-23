"""wisekiosk.service, the WiseKiosk app's backend."""

import contextlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

from board.unit import Unit

if TYPE_CHECKING:
    from wisebench.proxy import Proxy


# the CA the replay proxy signs its answers with, as mitmproxy writes it on the test host
_PROXY_CA_PATH = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
_PROXY_CA_BOARD_PATH = "/tmp/replay-ca.pem"


class Backend(Unit):
    """wisekiosk.service on the board: its process, and the replay proxy it can run behind.

    Each change registers its undo on the board's cleanup once it has taken.
    """

    _DROP_IN_DIR = "/run/systemd/system/wisekiosk.service.d"
    _PROXY_DROP_IN = f"{_DROP_IN_DIR}/replay.conf"
    # covers a daemon-reload plus a backend start
    _RELOAD_TIMEOUT_SECONDS = 60
    _RUNTIME_OVERRIDES_SWEEP = (
        f"if [ -d {_DROP_IN_DIR} ] || "
        '[ "$(systemctl is-enabled wisekiosk.service)" = masked-runtime ]; then '
        f"rm -rf {_DROP_IN_DIR}; systemctl unmask --runtime wisekiosk.service; "
        "systemctl daemon-reload; systemctl start wisekiosk.service; fi"
    )

    def clear_runtime_overrides(self) -> None:
        """Remove the runtime drop-ins and the runtime mask a dead run left on the backend, and start it."""
        self._board.run(self._RUNTIME_OVERRIDES_SWEEP, check=True, timeout=self._RELOAD_TIMEOUT_SECONDS)

    def pid(self, retry_for: float | None = None) -> str:
        """Read the backend's MainPID as systemd reports it.

        Args:
            retry_for: how long to retry through a dropped session, as `Board.run` takes it; None reads once.

        Returns:
            The MainPID.
        """
        return self._board.run(
            "systemctl show -p MainPID --value wisekiosk.service", check=True, retry_for=retry_for
        ).text

    def put_behind(self, proxy: "Proxy", config: str | os.PathLike[str]) -> None:
        """Put the backend behind `proxy`, running the replay set's `config`, until the test ends.

        A tunnel, the proxy's CA and a drop-in point wisekiosk.service at the proxy; then
        `board.app.config.use(config)` restarts the backend onto it before the browser starts. When the
        test ends the tunnel's steps are undone first, last first, then the config's, so the backend
        never runs behind a proxy that has gone.

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
