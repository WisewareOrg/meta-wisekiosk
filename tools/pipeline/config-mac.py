#!/usr/bin/env python3
"""Keyed hash of stdin, under the key named on the command line.

    ssh ... cat /data/config/config.json | python3 tools/pipeline/config-mac.py <keyfile>
        -- print the hex HMAC-SHA256 of stdin's bytes, keyed by <keyfile>'s contents

rc 2 if <keyfile> is missing or cannot be read.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "meta-wisekiosk" / "lib"))
from wisekiosk import record  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("usage: config-mac.py <keyfile>", file=sys.stderr)
        return 2
    try:
        key = Path(sys.argv[1]).read_bytes()
    except OSError as exc:
        print(f"config-mac.py: cannot read {sys.argv[1]}: {exc}", file=sys.stderr)
        return 2
    data = sys.stdin.buffer.read()
    print(record.keyed_hash(key, data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
