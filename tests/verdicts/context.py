"""Pure parsers for the device context the target suite records on every test. Text in, a plain
value out: no board, no file, no network.
"""

import re

_SHA256SUM_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")
_MODE_LINE = re.compile(r"^\s+(\d+x\d+)\s+(.*)$")


def file_hashes(sha256sum_output, paths):
    """Each path's sha256, or "absent" for a path `sha256sum` printed no line for.

    `sha256sum` exits 1 when a file is missing but still prints the others.

    Args:
        sha256sum_output (str): `<hash>  <path>` lines.
        paths (list[str]): the paths asked for.

    Returns:
        dict[str, str]: `paths` mapped to their hash or "absent".
    """
    found = {}
    for line in sha256sum_output.splitlines():
        match = _SHA256SUM_LINE.match(line)
        if match:
            found[match.group(2)] = match.group(1)
    return {path: found.get(path, "absent") for path in paths}


def display_mode(xrandr_output):
    """The current display mode as `<WxH>@<rate>`.

    Args:
        xrandr_output (str): `xrandr`'s output, where the current mode's rate carries `*`.

    Returns:
        str: `<WxH>@<rate>` from the first mode line whose rate carries `*`, or "none".
    """
    for line in xrandr_output.splitlines():
        match = _MODE_LINE.match(line)
        if not match:
            continue
        for rate in match.group(2).split():
            if "*" in rate:
                return f"{match.group(1)}@{rate.rstrip('*+')}"
    return "none"


def webkit_env(environ_text):
    """Every `WEBKIT_*` line in a `/proc/<pid>/environ` dump, comma-joined.

    Args:
        environ_text (str): the dump, NUL already converted to newline.

    Returns:
        str: every line starting `WEBKIT_`, in order, joined with commas.
    """
    return ",".join(line for line in environ_text.splitlines() if line.startswith("WEBKIT_"))
