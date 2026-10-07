"""The run record: R-line builders and the parsers/scrubbers that feed them
(design.md section 4). Every function here is pure: text or bytes in, text
or a tuple out, no board, no file, no network.
"""
import datetime
import hashlib
import hmac
import json
import re

_BUILDINFO_LINE = re.compile(r"^meta-wisekiosk\s*=\s*(\S+)", re.MULTILINE)
_BOOTED_BOOTNAME = re.compile(r"^RAUC_SYSTEM_BOOTED_BOOTNAME='(.*)'$", re.MULTILINE)
_SLOT_STATE = re.compile(r"^RAUC_SLOT_STATE_(\d+)='([^']*)'$", re.MULTILINE)
_RFC1918 = re.compile(
    r"^(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3})$"
)
_ASSET_TAG = re.compile(r'<script\b[^>]*\ssrc="([^"]+)"|<link\b[^>]*\shref="([^"]+)"')
_LEAK_KEYS = ("location", "parks")


def parse_buildinfo(text):
    """(branch, sha) from /etc/buildinfo's "meta-wisekiosk = <branch>:<sha>[ -- modified]"
    line (image-buildinfo's "%-17s = %s:%s%s" per layer), or ("", "") if no such line."""
    m = _BUILDINFO_LINE.search(text.replace("\r", ""))
    if not m:
        return "", ""
    branch, _, sha = m.group(1).rpartition(":")
    return branch, sha


def booted_slot(text):
    """The booted slot's bootname from `rauc status --output-format=shell`'s
    RAUC_SYSTEM_BOOTED_BOOTNAME line, or "" if absent."""
    m = _BOOTED_BOOTNAME.search(text)
    return m.group(1) if m else ""


def slot_installed_at(text):
    """The booted slot's install timestamp from `rauc status --detailed
    --output-format=shell`'s RAUC_SLOT_STATE_<n>/RAUC_SLOT_STATUS_INSTALLED_
    TIMESTAMP_<n> lines. Raises ValueError if no slot is booted, or the
    booted slot carries no install timestamp."""
    index = next((m.group(1) for m in _SLOT_STATE.finditer(text) if m.group(2) == "booted"), None)
    if index is None:
        raise ValueError("no booted slot in rauc status output")
    timestamp = re.search(
        r"^RAUC_SLOT_STATUS_INSTALLED_TIMESTAMP_" + index + r"='([^']*)'$", text, re.MULTILINE)
    if not timestamp:
        raise ValueError(f"booted slot {index} has no install timestamp")
    return timestamp.group(1)


def boot_ordinal(boots_json, installed_at):
    """The count of `journalctl --list-boots -o json` entries whose
    first_entry (microseconds since the epoch) is at or after installed_at
    (an ISO 8601 instant). Raises ValueError on unparseable input."""
    boots = json.loads(boots_json)
    threshold = datetime.datetime.fromisoformat(installed_at)
    return sum(
        1 for boot in boots
        if datetime.datetime.fromtimestamp(boot["first_entry"] / 1e6, tz=datetime.timezone.utc)
        >= threshold
    )


def keyed_hash(key, data):
    """Hex HMAC-SHA256 of data under key. Never embeds key in its output."""
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def scrub_argv(argv, target):
    """argv joined with spaces, the target token and every RFC1918 token
    replaced by "<target>"."""
    return " ".join(
        "<target>" if token == target or _RFC1918.match(token) else token
        for token in argv
    )


def asset_hashes(html):
    """The content-hash token of every <script src> / <link href> asset
    reference in html, in document order (the dash-delimited segment
    before the file extension)."""
    hashes = []
    for m in _ASSET_TAG.finditer(html):
        url = m.group(1) or m.group(2)
        stem = url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        hashes.append(stem.rsplit("-", 1)[-1])
    return hashes


def _without_leaks(value):
    if isinstance(value, dict):
        return {k: _without_leaks(v) for k, v in value.items() if k not in _LEAK_KEYS}
    if isinstance(value, list):
        return [_without_leaks(v) for v in value]
    return value


def config_summary(text):
    """config.json's shape with its location and parks keys removed,
    compact and space-free: module names, region names and every other
    option, including interval values -- no coordinates, no park names."""
    config = json.loads(text)
    return json.dumps(_without_leaks(config), separators=(",", ":"), sort_keys=True)


def tool_line(name, tool_commit, dirty, argv):
    return f"R tool={name} tool_commit={tool_commit} dirty={dirty} argv={argv}"


def board_line(role, boot_id, boot_ordinal, uptime_s, start, end):
    return (
        f"R board={role} hostname_check=ok boot_id={boot_id} "
        f"boot_ordinal={boot_ordinal} uptime_s={uptime_s} start={start} end={end}"
    )


def image_line(sha, slot):
    return f"R image={sha} slot={slot}"


def app_line(bundle, config_mac, config):
    return f"R app bundle={bundle} config_mac={config_mac} config={config}"


def sut_line(browser, nrestarts, cmdline_sha, webkit_env, kiosk_conf_mac, mode,
             kernel, cpufreq_max, timesync):
    return (
        f"R sut browser={browser} nrestarts={nrestarts} cmdline_sha={cmdline_sha} "
        f"webkit_env={webkit_env} kiosk_conf_mac={kiosk_conf_mac} mode={mode} "
        f"kernel={kernel} cpufreq_max={cpufreq_max} timesync={timesync}"
    )


def page_line(nonce, state, cards, faulted, unreachable):
    return f"R page nonce={nonce} state={state} cards={cards} faulted={faulted} unreachable={unreachable}"
