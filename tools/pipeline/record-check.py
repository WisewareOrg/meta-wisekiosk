#!/usr/bin/env python3
"""Checks a testimage run's record precondition, importing the package
exactly as config-mac.py does.

    python3 tools/pipeline/record-check.py <testresults.json> <sha>
        [--expect-cards <token>] [--replay <value>]
        -- print one line run.sh reads whole with a single `read`:
           "<status> <image> <dirty> <transport> <cards> <reason...>"

status is OK or ERROR. image and dirty are the record's own tool/image
fields ("-" if the record could not be read at all); dirty, transport and
cards are "0"/"1", or "-" for cards when --expect-cards was not given.
reason is empty on a clean OK, the rest of the line otherwise (may contain
spaces -- it is always the last field).

--expect-cards compares the record's own cards= token (the applied case's
page.<case id> line) against <token>; a mismatch sets cards=1. --replay
writes "R replay=<value>" into the record as a new "replay" key and
persists testresults.json with it, before this script's own stdout line is
printed -- the record of record gains the field, not only the report.

Always exits 0: the record's own malformed-ness is the caller's decision,
this script only reports it.
"""
import argparse
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


def _observed_cards(rec):
    for key, value in rec.items():
        if key.startswith("page.") and isinstance(value, str):
            m = re.search(r"cards=(\S+)", value)
            if m:
                return m.group(1)
    return None


def check(results_path, sha, expect_cards=None, replay=None):
    try:
        data = json.loads(Path(results_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"ERROR - - - - could not read the run record: {exc}"

    rec = _find_record(data)
    tool_val = rec.get("tool") if isinstance(rec, dict) else None
    image_val = rec.get("image") if isinstance(rec, dict) else None
    if not isinstance(tool_val, str) or not isinstance(image_val, str):
        return "ERROR - - - - no run record"

    image_m = re.search(r"image=(\S+)", image_val)
    dirty_m = re.search(r"dirty=(\S+)", tool_val)
    image = image_m.group(1) if image_m else "-"
    dirty = dirty_m.group(1) if dirty_m else "-"
    if dirty not in ("0", "1"):
        return f"ERROR - {dirty} - - run record names dirty={dirty}, not 0 or 1"
    transport = "1" if any(
        key.startswith("page.") and isinstance(value, str) and record.TRANSPORT_STATE in value
        for key, value in rec.items()) else "0"

    cards = "-"
    if expect_cards:
        observed = _observed_cards(rec)
        cards = "0" if observed is not None and record.parse_cards(observed) == record.parse_cards(expect_cards) \
            else "1"

    if replay is not None:
        rec["replay"] = record.replay_line(replay)
        Path(results_path).write_text(json.dumps(data), encoding="utf-8")

    if image != sha:
        return f"ERROR {image} {dirty} {transport} {cards} run record names image={image}, not {sha}"
    return f"OK {image} {dirty} {transport} {cards}"


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("results_path")
    parser.add_argument("sha")
    parser.add_argument("--expect-cards", default=None)
    parser.add_argument("--replay", default=None)
    try:
        args = parser.parse_args(sys.argv[1:])
    except SystemExit:
        print("usage: record-check.py <testresults.json> <sha> [--expect-cards <token>] [--replay <value>]",
              file=sys.stderr)
        return 0
    print(check(args.results_path, args.sha, args.expect_cards, args.replay))
    return 0


if __name__ == "__main__":
    sys.exit(main())
