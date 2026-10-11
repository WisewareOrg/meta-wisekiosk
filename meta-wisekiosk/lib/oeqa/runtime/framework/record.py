"""The run record: R-line builders and the parsers/scrubbers that feed them
(docs/testing.md names what the record carries). Every function here is
pure: text or bytes in, text or a tuple out, no board, no file, no network.
"""
import datetime
import hashlib
import hmac
import json
import re

# The run's own extraresults key, and the state a declared transport failure's
# page.<case id> line carries -- one spelling, every reader imports it.
RECORD_KEY = "wisekiosk.record"
TRANSPORT_STATE = "error:transport"

_BUILDINFO_LINE = re.compile(r"^meta-wisekiosk\s+=\s+(\S+)", re.MULTILINE)
_BOOTED_BOOTNAME = re.compile(r"^RAUC_SYSTEM_BOOTED_BOOTNAME='(.*)'$", re.MULTILINE)
_SLOT_STATE = re.compile(r"^RAUC_SLOT_STATE_(\d+)='([^']*)'$", re.MULTILINE)
_RFC1918 = re.compile(
    r"^(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3})$"
)
_ASSET_TAG = re.compile(r'<script\b[^>]*\ssrc="([^"]+)"|<link\b[^>]*\shref="([^"]+)"')
_BOOTED_INTO = re.compile(r"Booted into rootfs\.\d+ \(([^)]+)\)")


def parse_buildinfo(text):
    """The sha from /etc/buildinfo's "meta-wisekiosk = <branch>:<sha>[ -- modified]"
    line (image-buildinfo's "%-17s = %s:%s%s" per layer), or "" if no such line."""
    m = _BUILDINFO_LINE.search(text.replace("\r", ""))
    if not m:
        return ""
    return m.group(1).rpartition(":")[-1]


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


def boot_ordinal(journal_json_lines, installed_at, booted_bootname):
    """The count of rauc.service's own "Booted into rootfs.<n> (<slot>)"
    journal entries (one `journalctl -u rauc.service -o json
    --output-fields=_BOOT_ID,MESSAGE,__REALTIME_TIMESTAMP` read, one JSON
    object per line) whose slot is booted_bootname and whose own
    __REALTIME_TIMESTAMP (a string, microseconds since the epoch) is at
    or after installed_at (an ISO 8601 instant) -- never a boot's
    `--list-boots` first_entry, which the early-boot clock can floor
    before NTP syncs. A line that fails to parse, carries no
    __REALTIME_TIMESTAMP, or whose MESSAGE names no slot, is skipped,
    never guessed. Raises ValueError if installed_at is unparseable."""
    threshold = datetime.datetime.fromisoformat(installed_at)
    count = 0
    for line in journal_json_lines.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = entry.get("MESSAGE")
        realtime = entry.get("__REALTIME_TIMESTAMP")
        if not isinstance(message, str) or not realtime:
            continue
        m = _BOOTED_INTO.search(message)
        if not m or m.group(1) != booted_bootname:
            continue
        try:
            when = datetime.datetime.fromtimestamp(int(realtime) / 1e6, tz=datetime.timezone.utc)
        except (ValueError, TypeError):
            continue
        if when >= threshold:
            count += 1
    return count


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


def config_summary(text):
    """config.json's location-free summary: every placement's module and
    region name, plus its interval-shaped options only (keys ending
    "_seconds") -- an option this allowlist does not name is excluded by
    construction, never passed through, so no coordinate, park identifier
    or future option leaks onto the public report it renders into."""
    config = json.loads(text)
    modules = [
        {
            "module": placement.get("module"),
            "region": placement.get("region"),
            "options": {
                key: value for key, value in placement.get("options", {}).items()
                if key.endswith("_seconds")
            },
        }
        for placement in config.get("modules", [])
    ]
    return json.dumps({"modules": modules}, separators=(",", ":"), sort_keys=True)


def decode_hex_dump(dump):
    """Bytes from a device-transported hex dump -- `od -An -tx1 -v`
    (space/newline-separated pairs) or `hexdump -ve '1/1 "%02x"'` (one
    continuous run), either layout tolerated: busybox has no base64 applet,
    so hex is the byte-safe transport, and whitespace carries no meaning."""
    return bytes.fromhex(re.sub(r"\s+", "", dump))


def uptime_seconds(text):
    """The whole-second floor of /proc/uptime's own first field
    ("<uptime> <idle>\\n")."""
    return int(float(text.split()[0]))


def webkit_env(text):
    """Every WEBKIT_* line in text (a /proc/<pid>/environ dump, NUL already
    converted to newline), in order, comma-joined."""
    return ",".join(line for line in text.splitlines() if line.startswith("WEBKIT_"))


def kiosk_conf_mac(status, text, key):
    """keyed_hash of /data/config/kiosk.conf's bytes when status is 0 (the
    file was read); "absent" for any other status (EnvironmentFile=-
    treats a missing file as optional)."""
    if status != 0:
        return "absent"
    return keyed_hash(key, text.encode())


def tool_name(argv0):
    """"oe-test" when argv0's basename is oe-test (a hand run); "testimage"
    for anything else, including bitbake-worker and an empty argv0."""
    return "oe-test" if argv0.rpartition("/")[-1] == "oe-test" else "testimage"


def dirty(porcelain):
    """1 if `git status --porcelain` produced any non-whitespace output,
    else 0."""
    return 1 if porcelain.strip() else 0


def pid_from_pgrep(output):
    """`pgrep -x <name>`'s first pid line. Raises ValueError if output is
    empty (no such process), rather than an IndexError on an empty split."""
    lines = output.splitlines()
    if not lines:
        raise ValueError("pgrep produced no output")
    return lines[0]


def hostname_mismatch(observed, expected):
    """The bench-only refusal message when observed != expected, else None."""
    if observed == expected:
        return None
    return (
        f"the board's live hostname ({observed!r}) does not match "
        f"the expected KIOSK_TARGET_HOSTNAME ({expected!r}) -- refusing to "
        "run against a board this suite did not expect")


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


def perf_line(fps, p50, stall, maxstall, ttp, rss, idle, thermal, cost):
    return (
        f"R perf fps={fps} p50={p50} stall={stall} maxstall={maxstall} ttp={ttp} "
        f"rss={rss} idle={idle} thermal={thermal} cost={cost}"
    )


def mode_token(environ_text, port):
    """"live" if environ_text (a /proc/<pid>/environ dump, NUL already
    newline) carries no HTTPS_PROXY line; "replay" if it carries exactly
    one line equal to this job's own proxy; None for anything else -- an
    unexpected or missing-vs-present mismatch, always a void."""
    lines = [line for line in environ_text.splitlines() if line.startswith("HTTPS_PROXY=")]
    if not lines:
        return "live"
    if lines == [f"HTTPS_PROXY=http://127.0.0.1:{port}"]:
        return "replay"
    return None
