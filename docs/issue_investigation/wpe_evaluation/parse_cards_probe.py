#!/usr/bin/env python3
"""Parse cards-probe.js's CP| payload and gate a capture on "all 4 cards live".

  python3 parse_cards_probe.py <capture>   report sample count, c/l range, and the verdict

Payload: CP|t=<sec>|c=<n>|l=<n> -- c is [data-pwt-card] count, l is the count of those cards
that also hold [data-pwt-leaderboard] (i.e. actually rendered live data, not closed or
API-failed). The gate is c=4 and l=4; see parse_cards_probe_test.py's header for why c/l
short of 4 must VOID a run rather than read as "fine".
"""
import re
import sys

PAT = re.compile(r"CP\|t=(\d+)\|c=(\d+)\|l=(\d+)")
KEYS = ("t", "c", "l")


def parse(line):
    """One CP| payload line -> dict, or None if the line holds no complete payload."""
    m = PAT.search(line)
    return dict(zip(KEYS, (int(x) for x in m.groups()))) if m else None


def samples_of(lines):
    return [d for d in map(parse, lines) if d]


def all_live(lines):
    """True iff every parseable CP| sample shows c=4 and l=4. Raises ValueError if NOTHING
    parsed -- a probe that never ran must never read as "all live", which is what an empty
    all()-over-nothing would otherwise give."""
    ds = samples_of(lines)
    if not ds:
        raise ValueError("no CP| samples")
    return all(d["c"] == 4 and d["l"] == 4 for d in ds)


def all_at_least(lines, min_live):
    """True iff every parseable CP| sample shows l >= min_live (a relaxed gate for a window
    where a park is legitimately closed, e.g. min_live=3 lets one closed card through while
    still VOIDing a run where a SECOND card also drops out mid-capture). Raises ValueError on
    zero samples, same reasoning as all_live."""
    ds = samples_of(lines)
    if not ds:
        raise ValueError("no CP| samples")
    return all(d["l"] >= min_live for d in ds)


def live_fraction(lines):
    """Fraction of parseable samples with l=4 (soak reporting). Raises on zero samples."""
    ds = samples_of(lines)
    if not ds:
        raise ValueError("no CP| samples")
    return sum(1 for d in ds if d["l"] == 4) / len(ds)


def main(path):
    lines = open(path).read().splitlines()
    ds = samples_of(lines)
    if not ds:
        print("samples 0 -- VOID: no CP| payloads parsed")
        return
    cs = sorted(d["c"] for d in ds)
    ls = sorted(d["l"] for d in ds)
    verdict = "LIVE (c=4 l=4 throughout)" if all_live(lines) else "VOID (not c=4 l=4 throughout)"
    print(f"samples {len(ds)}  c range [{cs[0]},{cs[-1]}]  l range [{ls[0]},{ls[-1]}]  "
          f"live_fraction={live_fraction(lines):.3f}  {verdict}")


if __name__ == "__main__":
    main(sys.argv[1])
