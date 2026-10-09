#!/usr/bin/env python3
"""Checks a testimage run's record precondition, importing the package
exactly as config-mac.py does.

    python3 tools/pipeline/record-check.py <testresults.json> <sha> [--replay <value>]
        -- print one line run.sh reads whole with a single `read`:
           "<status> <image> <dirty> <transport> <reason...>"

status is OK or ERROR. image and dirty are the record's own tool/image
fields ("-" if the record could not be read at all); dirty and transport
are "0"/"1". reason is empty on a clean OK, the rest of the line otherwise
(may contain spaces -- it is always the last field).

--replay writes "R replay=<value>" into the record as a new "replay" key
and persists testresults.json with it, before this script's own stdout
line is printed -- the record of record gains the field, not only the
report.

Always exits 0: the record's own malformed-ness is the caller's decision,
this script only reports it.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "meta-wisekiosk" / "lib" / "oeqa" / "runtime"))
from framework import record  # noqa: E402


def _find_record(data):
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, dict):
                result = value.get("result")
                if isinstance(result, dict) and record.RECORD_KEY in result:
                    return result[record.RECORD_KEY]
    return None


def check(results_path, sha, replay=None):
    try:
        data = json.loads(Path(results_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"ERROR - - - could not read the run record: {exc}"

    rec = _find_record(data)
    tool_val = rec.get("tool") if isinstance(rec, dict) else None
    image_val = rec.get("image") if isinstance(rec, dict) else None
    if not isinstance(tool_val, str) or not isinstance(image_val, str):
        return "ERROR - - - no run record"

    image_m = re.search(r"image=(\S+)", image_val)
    dirty_m = re.search(r"dirty=(\S+)", tool_val)
    image = image_m.group(1) if image_m else "-"
    dirty = dirty_m.group(1) if dirty_m else "-"
    if dirty not in ("0", "1"):
        return f"ERROR - {dirty} - run record names dirty={dirty}, not 0 or 1"
    transport = "1" if any(
        key.startswith("page.") and isinstance(value, str) and record.TRANSPORT_STATE in value
        for key, value in rec.items()) else "0"

    if replay is not None:
        rec["replay"] = f"R replay={replay}"
        Path(results_path).write_text(json.dumps(data), encoding="utf-8")

    if image != sha:
        return f"ERROR {image} {dirty} {transport} run record names image={image}, not {sha}"
    return f"OK {image} {dirty} {transport}"


def main():
    argv = sys.argv[1:]
    if len(argv) < 2:
        print("usage: record-check.py <testresults.json> <sha> [--replay <value>]", file=sys.stderr)
        return 0
    results_path, sha, rest = argv[0], argv[1], argv[2:]
    replay = None
    i = 0
    while i < len(rest) - 1:
        if rest[i] == "--replay":
            replay = rest[i + 1]
        i += 2
    print(check(results_path, sha, replay))
    return 0


if __name__ == "__main__":
    sys.exit(main())
