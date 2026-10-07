#!/usr/bin/env python3
"""Keyed hash of a device-transported hex dump, under the key named on the
command line. The same decode wisekiosk.record uses for the run record, so
the two agree on a boundary value by construction, not by copy.

    ssh ... hexdump -ve '1/1 "%02x"' /data/config/config.json \\
        | python3 tools/pipeline/config-mac.py <keyfile>
        -- print the hex HMAC-SHA256 of the dump's decoded bytes, keyed by
           <keyfile>'s contents

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
    data = record.decode_hex_dump(sys.stdin.read())
    print(record.keyed_hash(key, data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
