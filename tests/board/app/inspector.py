"""The browser's remote inspector, which runs JavaScript in the page it shows."""

import json
import subprocess
from pathlib import Path

from board.part import Part

_REPO = Path(__file__).resolve().parents[3]
_CLIENT = ("uv", "run", "--locked", "tools/kiosk-inspect.py")
# the client's exit when there is no page to evaluate in
_NO_PAGE = 3
_TIMEOUT_SECONDS = 60
_PORT = 2999


class NoPageError(Exception):
    """There is no page to evaluate in."""


class Inspector(Part):
    """WebKit's remote inspector on the board, reached through a forwarded port by `tools/kiosk-inspect.py`.

    Attributes:
        ENVIRONMENT: the browser's environment variable that turns the inspector on.
    """

    ENVIRONMENT = f"WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:{_PORT}"

    def evaluate(self, script: str) -> object:
        """Evaluate `script` in the page.

        Args:
            script: the JavaScript.

        Returns:
            Its value, as JSON carries it; None for a value that is not JSON.

        Raises:
            NoPageError: there is no page to evaluate in.
        """
        with self._board.forward_local_port(_PORT) as port:
            client = subprocess.run(
                [*_CLIENT, str(port)],
                cwd=_REPO,
                input=script,
                stdout=subprocess.PIPE,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        if client.returncode == _NO_PAGE:
            raise NoPageError
        client.check_returncode()
        return json.loads(client.stdout)
