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
    """wisekiosk.service on the board, which can run behind a replay proxy."""

    def put_behind(self, proxy: "Proxy", config: str | os.PathLike[str]) -> None:
        """Put the backend behind `proxy`, running the replay set's `config`, until the test ends.

        A tunnel, the proxy's CA and a drop-in point the backend at the proxy; then
        `board.app.config.use(config)` restarts the backend onto it before the browser starts. When the
        test ends the tunnel's steps are undone first, last first, then the config's, whose backend
        restart drops the proxy settings; until it, the backend points at a proxy that has gone.

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
            self.drop_in(
                f"[Service]\\nEnvironment=HTTPS_PROXY=http://127.0.0.1:{proxy.port}\\n"
                f"Environment=SSL_CERT_FILE={_PROXY_CA_BOARD_PATH}\\n",
                cleanup=tunnel,
            )
            board.app.config.use(config)
        finally:
            board.cleanup.push(tunnel)
