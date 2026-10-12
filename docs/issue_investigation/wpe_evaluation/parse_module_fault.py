#!/usr/bin/env python3
"""Parse mf-probe.js's MF| payload and summarise a soak's samples.

  python3 parse_module_fault.py <capture>   summarise every MF| line in a capture

Payload and field meanings: parse_module_fault_test.py's header.
"""
import re
import sys

PAT = re.compile(r"MF\|t=(\d+)\|f=(\d+)\|fmax=(\d+)\|fever=(\d+)\|u=(\d+)\|umax=(\d+)")
KEYS = ("t", "f", "fmax", "fever", "u", "umax")


def parse(line):
    """One MF| payload line -> dict, or None if the line holds no complete payload."""
    m = PAT.search(line)
    return dict(zip(KEYS, (int(x) for x in m.groups()))) if m else None


def soak_summary(lines):
    """Peak fmax/fever/umax over every parseable sample; unparseable lines are skipped."""
    ds = [d for d in map(parse, lines) if d]
    if not ds:
        raise ValueError("no MF| samples")
    return {k: max(d[k] for d in ds) for k in ("fmax", "fever", "umax")}


def main(path):
    lines = open(path).read().splitlines()
    n = sum(1 for l in lines if parse(l))
    print(f"samples {n}  {soak_summary(lines)}")


if __name__ == "__main__":
    main(sys.argv[1])
