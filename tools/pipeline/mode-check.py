#!/usr/bin/env python3
"""Prints the live/replay mode token for one backend environ dump,
importing the package exactly as config-mac.py does.

    python3 tools/pipeline/mode-check.py <proxy-url>
        -- reads a /proc/<pid>/environ dump (NUL already newline) on stdin,
           prints "live", "replay" or "void"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "meta-wisekiosk" / "lib" / "oeqa" / "runtime"))
from framework import record  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("usage: mode-check.py <proxy-url>", file=sys.stderr)
        return 2
    print(record.mode_token(sys.stdin.read(), sys.argv[1]) or "void")
    return 0


if __name__ == "__main__":
    sys.exit(main())
