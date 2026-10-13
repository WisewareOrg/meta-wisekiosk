"""Whether the backend process's environment names a live or replay HTTPS_PROXY. Pure: no
device, no file -- the environment dump and port are both plain values.
"""


def mode_token(environ_text, port):
    """The backend's replay mode, from its own `/proc/<pid>/environ` dump.

    Args:
        environ_text (str): The backend process's environment, one `KEY=VALUE` pair per line
            (NUL already converted to newline).
        port (int): The proxy's own loopback port, matched against `HTTPS_PROXY`'s value.

    Returns:
        str | None: `"live"` if `environ_text` carries no `HTTPS_PROXY` line; `"replay"` if it
            carries exactly one line equal to `HTTPS_PROXY=http://127.0.0.1:<port>`; `None` for
            anything else -- an unexpected or missing-vs-present mismatch, always a void.
    """
    lines = [line for line in environ_text.splitlines() if line.startswith("HTTPS_PROXY=")]
    if not lines:
        return "live"
    if lines == [f"HTTPS_PROXY=http://127.0.0.1:{port}"]:
        return "replay"
    return None
