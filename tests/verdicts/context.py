"""Pure parsers for the device context `conftest.py`'s `device_context` fixture attaches to
every test's report. Every function here is pure -- text or bytes in, a plain value out, no
board, no file, no network. Ported from the pre-#224 `framework/record.py` (not carried onto
this stack by #224, which kept only `parse_buildinfo`/`keyed_hash`/`decode_hex_dump`).
"""

import json
import re

from framework.record import keyed_hash

_BOOTED_BOOTNAME = re.compile(r"^RAUC_SYSTEM_BOOTED_BOOTNAME='(.*)'$", re.MULTILINE)
_ASSET_TAG = re.compile(r'<script\b[^>]*\ssrc="([^"]+)"|<link\b[^>]*\shref="([^"]+)"')


def booted_slot(text):
    """The booted slot's bootname from `rauc status`'s own shell-format output.

    Args:
        text (str): `rauc status --output-format=shell`'s (or `--detailed`'s) stdout.

    Returns:
        str: The `RAUC_SYSTEM_BOOTED_BOOTNAME` line's value (e.g. `"rootfs.0"`), or `""` if
            absent.
    """
    m = _BOOTED_BOOTNAME.search(text)
    return m.group(1) if m else ""


def uptime_seconds(text):
    """The whole-second floor of `/proc/uptime`'s own first field.

    Args:
        text (str): `/proc/uptime`'s contents (`"<uptime> <idle>\\n"`).

    Returns:
        int: The uptime field, floored to the whole second.
    """
    return int(float(text.split()[0]))


def asset_hashes(html):
    """Every served asset's own content-hash token, in document order.

    Args:
        html (str): The served page's raw HTML.

    Returns:
        list[str]: The dash-delimited content-hash segment (before the file extension) of every
            `<script src>`/`<link href>` reference, in document order.
    """
    hashes = []
    for m in _ASSET_TAG.finditer(html):
        url = m.group(1) or m.group(2)
        stem = url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        hashes.append(stem.rsplit("-", 1)[-1])
    return hashes


def config_summary(text):
    """`config.json`'s location-free summary.

    Every placement's module and region name, plus its interval-shaped options only (keys
    ending `_seconds`) -- an option this allowlist does not name is excluded by construction,
    never passed through, so no coordinate, park identifier or future option leaks into a
    report built from this summary.

    Args:
        text (str): `config.json`'s raw text.

    Returns:
        str: A JSON string: `{"modules": [{"module": ..., "region": ..., "options": {...}}]}`.
    """
    config = json.loads(text)
    modules = [
        {
            "module": placement.get("module"),
            "region": placement.get("region"),
            "options": {
                key: value
                for key, value in placement.get("options", {}).items()
                if key.endswith("_seconds")
            },
        }
        for placement in config.get("modules", [])
    ]
    return json.dumps({"modules": modules}, separators=(",", ":"), sort_keys=True)


def webkit_env(text):
    """Every `WEBKIT_*` line in a `/proc/<pid>/environ` dump, comma-joined.

    Args:
        text (str): The dump, NUL already converted to newline.

    Returns:
        str: Every line starting `WEBKIT_`, in order, joined with commas.
    """
    return ",".join(line for line in text.splitlines() if line.startswith("WEBKIT_"))


def kiosk_conf_mac(status, text, key):
    """The keyed hash of `/data/config/kiosk.conf`'s bytes, or `"absent"` if unreadable.

    `EnvironmentFile=-` (the leading `-`) treats a missing `kiosk.conf` as optional, so its
    absence is a normal outcome here, not an error.

    Args:
        status (int): The read command's own exit status (0 means `text` holds the file).
        text (str): The file's decoded text, when `status` is 0.
        key (bytes): The HMAC key.

    Returns:
        str: `keyed_hash(key, text.encode())` when `status` is 0, else the literal `"absent"`.
    """
    if status != 0:
        return "absent"
    return keyed_hash(key, text.encode())


def pid_from_pgrep(output):
    """The first pid in `pgrep`'s own output.

    Args:
        output (str): `pgrep -x <name>`'s stdout.

    Returns:
        str: The first line.

    Raises:
        ValueError: `output` is empty (no such process).
    """
    lines = output.splitlines()
    if not lines:
        raise ValueError("pgrep produced no output")
    return lines[0]
