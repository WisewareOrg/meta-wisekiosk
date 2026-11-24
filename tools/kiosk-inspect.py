#!/usr/bin/env python3
"""Evaluate JavaScript in the page the kiosk's browser shows, through the browser's remote inspector.

    uv run --locked tools/kiosk-inspect.py PORT < SCRIPT

PORT is this host's port to the inspector. Prints the value as JSON, null for one that is not JSON.

It is connected only for the length of one evaluation, as a connected inspector slows the page, and
only to a page the inspector lists: connecting to one that is not there yet crashes the browser.

Exits 3 if there is no page to evaluate in: the inspector does not answer, lists no page, or refuses
or drops the connection; the reason goes to stderr. Anything else that fails is a traceback, exit 1.
"""

import http.client
import json
import re
import sys
from collections.abc import Iterator

import websocket

_TIMEOUT_SECONDS = 10
_CALL_ID = 1
_NO_PAGE = 3
_PAGE = re.compile(r"/socket/\d+/\d+/WebPage")


def listed_page(port: int) -> str:
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
        connection.request("GET", "/")
        page = _PAGE.search(connection.getresponse().read().decode())
    finally:
        connection.close()
    if page is None:
        raise EOFError("the inspector lists no page")
    return page[0]


def evaluate(port: int, script: str) -> object:
    """Evaluate `script` in the page the inspector lists.

    Args:
        port: the host's port to the inspector.
        script: the JavaScript.

    Returns:
        Its value, as JSON carries it; None for a value that is not JSON.
    """
    inspector = websocket.create_connection(
        f"ws://127.0.0.1:{port}{listed_page(port)}", timeout=_TIMEOUT_SECONDS, suppress_origin=True
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
        for message in messages:
            if message.get("method") == "Target.dispatchMessageFromTarget":
                answer = json.loads(message["params"]["message"])
                if answer.get("id") == _CALL_ID:
                    return answer.get("result", {}).get("result", {}).get("value")
    finally:
        inspector.shutdown()
    return None


def _messages(inspector: websocket.WebSocket) -> Iterator[dict]:
    """Read the inspector's messages as they arrive.

    Args:
        inspector: the connection to the inspector.

    Yields:
        dict: each message.

    Raises:
        EOFError: the inspector closed the connection.
    """
    # recv returns "" for a close
    while text := inspector.recv():
        yield json.loads(text)
    raise EOFError("the inspector closed the connection")


def main() -> None:
    """Evaluate the script on stdin, and print its value."""
    port, script = int(sys.argv[1]), sys.stdin.read()
    try:
        value = evaluate(port, script)
    except (OSError, EOFError, http.client.HTTPException, websocket.WebSocketException) as error:
        print(f"kiosk-inspect: no page: {error!r}", file=sys.stderr)
        sys.exit(_NO_PAGE)
    print(json.dumps(value))


if __name__ == "__main__":
    main()
