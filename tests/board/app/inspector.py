"""The browser's remote inspector, which runs JavaScript in the page it shows."""

import http.client
import json
import re
import sys
from collections.abc import Iterator
from typing import TYPE_CHECKING

import websocket

from board.part import Part

if TYPE_CHECKING:
    from board import Board

_PORT = 2999
_TIMEOUT_SECONDS = 10
_CALL_ID = 1
_PAGE = re.compile(r"/socket/\d+/\d+/WebPage")


class NoPageError(Exception):
    """There is no page to evaluate in."""


class Inspector(Part):
    """WebKit's remote inspector on the board, reached through a forwarded port.

    Attributes:
        ENVIRONMENT: the browser's environment variable that turns the inspector on.
    """

    ENVIRONMENT = f"WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:{_PORT}"

    def __init__(self, board: "Board") -> None:
        """Bind to the board, with no read failed.

        Args:
            board: the board under test.
        """
        super().__init__(board)
        self._no_page = ""

    def evaluate(self, script: str) -> object:
        """Evaluate `script` in the page.

        It is connected only for the length of one evaluation, as a connected inspector slows the page, and
        only to a page the inspector lists: connecting to one that is not there yet crashes the browser.

        Why there is no page goes to stderr each time it changes, as a wait takes the error as a read that
        does not hold.

        Args:
            script: the JavaScript.

        Returns:
            Its value, as JSON carries it; None for a value that is not JSON.

        Raises:
            NoPageError: the inspector does not answer, lists no page, refuses or drops the connection, or
                answers with an error, as while a page loads.
            RuntimeError: the script threw; its message is what it threw.
        """
        try:
            result = self._result(script)
        except NoPageError as error:
            if str(error) != self._no_page:
                self._no_page = str(error)
                print(f"no page: {error}", file=sys.stderr)
            raise
        self._no_page = ""
        value = result["result"]
        if result.get("wasThrown"):
            raise RuntimeError(value.get("description", value.get("value")))
        return value.get("value")

    def _result(self, script: str) -> dict:
        """Evaluate `script` in the page the inspector lists, through a forwarded port.

        Args:
            script: the JavaScript.

        Returns:
            What it evaluated to, and whether it threw.

        Raises:
            NoPageError: there is no page to evaluate in.
        """
        with self._board.forward_local_port(_PORT) as port:
            try:
                answer = _answer(port, script)
            except (OSError, http.client.HTTPException, websocket.WebSocketException) as error:
                raise NoPageError(f"the inspector did not answer: {error!r}") from error
        if "error" in answer:
            raise NoPageError(f"the inspector answered: {answer['error']['message']}")
        return answer["result"]


def _answer(port: int, script: str) -> dict:
    """Evaluate `script` in the page the inspector lists.

    Args:
        port: the host's port to the inspector.
        script: the JavaScript.

    Returns:
        The inspector's answer.
    """
    inspector = websocket.create_connection(
        f"ws://127.0.0.1:{port}{_listed_page(port)}", timeout=_TIMEOUT_SECONDS, suppress_origin=True
    )
    try:
        messages = _messages(inspector)
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
        inspector.send(json.dumps(to_page))
        answers = (
            json.loads(message["params"]["message"])
            for message in messages
            if message.get("method") == "Target.dispatchMessageFromTarget"
        )
        return next(answer for answer in answers if answer.get("id") == _CALL_ID)
    finally:
        inspector.shutdown()


def _listed_page(port: int) -> str:
    """Read the page the inspector lists.

    Args:
        port: the host's port to the inspector.

    Returns:
        The path of its WebSocket.

    Raises:
        NoPageError: it lists none.
    """
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_TIMEOUT_SECONDS)
    try:
        connection.request("GET", "/")
        page = _PAGE.search(connection.getresponse().read().decode())
    finally:
        connection.close()
    if page is None:
        raise NoPageError("the inspector lists no page")
    return page[0]


def _messages(inspector: websocket.WebSocket) -> Iterator[dict]:
    """Read the inspector's messages as they arrive.

    Args:
        inspector: the connection to the inspector.

    Yields:
        dict: each message.

    Raises:
        NoPageError: the inspector closed the connection.
    """
    # recv returns "" for a close
    while text := inspector.recv():
        yield json.loads(text)
    raise NoPageError("the inspector closed the connection")
