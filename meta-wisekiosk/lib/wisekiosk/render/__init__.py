"""The render-advancing verdict: a port of tools/kiosk-render-check.sh's
render_verdict over the same probe vocabulary, as a list of lines rather
than one shell string. Pure: no device, no subprocess.
"""
import re

MIN_BYTES = 100
EMPTY_MD5 = "d41d8cd98f00b204e9800998ecf8427e"

_FRAME_FIELDS = re.compile(r"^frame \d+\s+(.*)$")
_KV = re.compile(r"(\w+)=(\S+)")


def _fields(line):
    m = _FRAME_FIELDS.match(line)
    return dict(_KV.findall(m.group(1))) if m else {}


def verdict(lines):
    """(outcome, reason) for the two-capture render-advancing probe.
    outcome is one of "advancing", "frozen", "error"; reason is always set,
    and names the guard that fired for an "error" outcome."""
    if any(line == "cap import=0" for line in lines):
        return "error", "no import on the device, so no frame could be captured"

    frames = [line for line in lines if line.startswith("frame ")]
    if len(frames) != 2:
        return "error", f"the probe returned {len(frames)} frame line(s), not 2 -- nothing to compare"

    parsed = [_fields(line) for line in frames]

    if any(fields.get("rc", "0") != "0" for fields in parsed):
        errs = [fields["err"] for fields in parsed
                if fields.get("rc", "0") != "0" and fields.get("err")]
        detail = "; ".join(e for e in errs if e != "none")
        suffix = f" ({detail})" if detail else ""
        return "error", f"'import' exited non-zero on at least one frame -- see its rc field{suffix}"

    for fields in parsed:
        raw_bytes = fields.get("bytes")
        if raw_bytes is None or int(raw_bytes) < MIN_BYTES:
            return "error", f"a captured frame is under {MIN_BYTES} bytes -- too small to be a PNG"

    if any(fields.get("md5") == EMPTY_MD5 for fields in parsed):
        return "error", "a frame hashed to the md5 of empty input -- the capture produced no bytes"

    blank_line = next((line for line in lines if line.startswith("blank ")), None)
    blank = dict(_KV.findall(blank_line)) if blank_line else {}
    if blank.get("min") is not None and blank.get("min") == blank.get("max"):
        return "error", f"every pixel in the captured region is identical (min=max={blank['min']}) -- a uniform region carries no information"

    h1, h2 = parsed[0].get("md5"), parsed[1].get("md5")
    if not h1 or not h2:
        return "error", "a frame line carried no md5 field -- nothing was compared"

    if h1 == h2:
        return "frozen", f"both frames are byte-identical ({h1}) -- nothing repainted in the captured region"

    return "advancing", f"the two frames differ ({h1} / {h2}) -- the render repainted within the interval"
