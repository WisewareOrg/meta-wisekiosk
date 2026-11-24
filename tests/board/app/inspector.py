"""The browser's remote inspector, which runs JavaScript in the page it shows."""

import http.client
import json
import re
import socket
from collections.abc import Iterator

from wsproto import ConnectionType, WSConnection
from wsproto.events import CloseConnection, Message, RejectConnection, Request
from wsproto.utilities import RemoteProtocolError

from board.part import Part

_PORT = 2999
_TIMEOUT_SECONDS = 10
_CALL_ID = 1
_PAGE = re.compile(r"/socket/\d+/\d+/WebPage")


class Inspector(Part):
    """WebKit's remote inspector on the board, reached through a forwarded port.

    It is connected to only for the length of one evaluation, as a connected inspector slows the page, and
    only to a page it lists: connecting to one that is not there yet crashes the browser.

    Attributes:
        ENVIRONMENT: the browser's environment variable that turns the inspector on.
        ERRORS: what an evaluation raises when there is no page to evaluate in.
    """

    ENVIRONMENT = f"WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:{_PORT}"
    ERRORS = (OSError, EOFError, RemoteProtocolError, http.client.HTTPException)

    def evaluate(self, script: str) -> object:
        """Evaluate `script` in the page.

        Args:
            script: the JavaScript.

        Returns:
            Its value, as JSON carries it; None for a value that is not JSON.
        """
        with self._board.forward_local_port(_PORT) as port:
            target = self._listed_page(port)
            return self._evaluate_in(port, target, script)

    @staticmethod
    def _listed_page(port: int) -> str:
        """Read the page the inspector lists.

        Args:
            port: the host's port to the inspector.

        Returns:
            The path of its WebSocket.

        Raises:
            EOFError: it lists none.
        """
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_TIMEOUT_SECONDS)
        try:
            connection.request("GET", "/", headers={"Host": f"127.0.0.1:{_PORT}"})
            page = _PAGE.search(connection.getresponse().read().decode())
        finally:
            connection.close()
        if page is None:
            raise EOFError("the inspector lists no page")
        return page[0]

    def _evaluate_in(self, port: int, target: str, script: str) -> object:
        """Evaluate `script` in a page the inspector lists.

        Args:
            port: the host's port to the inspector.
            target: the path of the page's WebSocket.
            script: the JavaScript.

        Returns:
            Its value, as JSON carries it; None for a value that is not JSON.
        """
        with socket.create_connection(("127.0.0.1", port), _TIMEOUT_SECONDS) as connection:
            websocket = WSConnection(ConnectionType.CLIENT)
            connection.sendall(websocket.send(Request(host=f"127.0.0.1:{_PORT}", target=target)))
            messages = self._messages(connection, websocket)
            page = next(
                message["params"]["targetInfo"]["targetId"]
                for message in messages
                if message.get("method") == "Target.targetCreated" and message["params"]["targetInfo"]["type"] == "page"
            )
            call = {
                "id": _CALL_ID,
                "method": "Runtime.evaluate",
                "params": {"expression": script, "returnByValue": True},
            }
            to_page = {
                "id": _CALL_ID,
                "method": "Target.sendMessageToTarget",
                "params": {"targetId": page, "message": json.dumps(call)},
            }
            connection.sendall(websocket.send(Message(json.dumps(to_page))))
            for message in messages:
                if message.get("method") == "Target.dispatchMessageFromTarget":
                    answer = json.loads(message["params"]["message"])
                    if answer.get("id") == _CALL_ID:
                        return answer.get("result", {}).get("result", {}).get("value")
        return None

    @staticmethod
    def _messages(connection: socket.socket, websocket: WSConnection) -> Iterator[dict]:
        """Read the inspector's messages as they arrive.

        Args:
            connection: the socket to the inspector.
            websocket: the WebSocket on it.

        Yields:
            dict: each message.

        Raises:
            EOFError: the inspector closed or refused the connection.
        """
        text = ""
        while True:
            data = connection.recv(65536)
            if not data:
                raise EOFError("the inspector closed the connection")
            websocket.receive_data(data)
            for event in websocket.events():
                if isinstance(event, CloseConnection | RejectConnection):
                    raise EOFError("the inspector closed or refused the connection")
                if isinstance(event, Message):
                    text += event.data
                    if event.message_finished:
                        yield json.loads(text)
                        text = ""
