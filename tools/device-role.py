#!/usr/bin/env python3
"""Resolve a board's role and hostname from local/device-identity.md.

    device-role.py <address>    -- print "role=<r> hostname=<h>", rc 1 on no match

The single definition `oe-test.sh` and `install.sh` both called inline before
this file existed. Parses the map's ```identity fence the same way
tools/scrub-identity.py does (FENCE_OPEN/FENCE_CLOSE/MAP_ROW), so prose outside
the fence cannot register a false match.
"""
import re
import sys
from pathlib import Path

FENCE_OPEN = re.compile(r'^```identity\s*$')
FENCE_CLOSE = re.compile(r'^```\s*$')
MAP_ROW = re.compile(r'^\s*([A-Za-z0-9_.]+)\s*=\s*(\S.*?)\s*$')


def resolve_role(fence_text, address):
    """(role, hostname) for the role whose "<role>.address" row equals
    address, scanning only fence_text's ```identity fence. Raises
    ValueError naming address if no role's address matches."""
    rows, inside = {}, False
    for line in fence_text.splitlines():
        if not inside:
            if FENCE_OPEN.match(line):
                inside = True
            continue
        if FENCE_CLOSE.match(line):
            break
        m = MAP_ROW.match(line)
        if m:
            rows[m.group(1)] = m.group(2)

    for key, value in rows.items():
        if key.endswith(".address") and value == address:
            role = key[: -len(".address")]
            return role, rows.get(f"{role}.hostname", "")
    raise ValueError(f"no role in the map has address {address}")


def main():
    if len(sys.argv) != 2:
        print("usage: device-role.py <address>", file=sys.stderr)
        return 2
    address = sys.argv[1]
    root = Path(__file__).resolve().parent.parent
    map_path = root / "local" / "device-identity.md"
    try:
        fence_text = map_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"device-role.py: cannot read {map_path}: {exc}", file=sys.stderr)
        return 1
    try:
        role, hostname = resolve_role(fence_text, address)
    except ValueError as exc:
        print(f"device-role.py: {exc}", file=sys.stderr)
        return 1
    print(f"role={role} hostname={hostname}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
