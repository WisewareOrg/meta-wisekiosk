#!/usr/bin/env python3
"""Resolve a board role to its bare address from the site's identity map.

    resolve-role.py [--map <path>] bench

Only `bench` resolves. Any other role, no role, extra arguments, a missing
--map file, or a map with no `bench.address` row: rc 2, nothing on stdout,
the reason on stderr.

--map defaults to <repo root>/local/device-identity.md, the repo root found
by `git rev-parse --show-toplevel` from the current directory. The map's
```identity fence and `key = value` row format is defined in
tools/scrub-identity.py.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent

# Loaded by path (see tools/artifact-diff.py): a hyphenated filename is not
# a normal import. Provides git_env().
_spec = importlib.util.spec_from_file_location(
    "layer_currency", TOOLS / "layer-currency.py")
_layer_currency = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_layer_currency)
git_env = _layer_currency.git_env

ROLE = "bench"
ROLE_KEY = "bench.address"

FENCE_OPEN = re.compile(r'^```identity\s*$')
FENCE_CLOSE = re.compile(r'^```\s*$')
MAP_ROW = re.compile(r'^\s*([A-Za-z0-9_.]+)\s*=\s*(\S.*?)\s*$')


def refuse(reason):
    print(reason, file=sys.stderr)
    return 2


def default_map():
    """<repo root>/local/device-identity.md, or None with no repo found."""
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, env=git_env())
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()) / "local" / "device-identity.md"


def read_row(map_path, key):
    """The value of `key` inside map_path's ```identity fence, or None."""
    try:
        text = map_path.read_text(encoding="utf-8")
    except OSError:
        return None
    inside = False
    for line in text.splitlines():
        if not inside:
            if FENCE_OPEN.match(line):
                inside = True
            continue
        if FENCE_CLOSE.match(line):
            break
        m = MAP_ROW.match(line)
        if m and m.group(1) == key:
            return m.group(2)
    return None


def main():
    argv = sys.argv[1:]
    if argv == ["--help"]:
        print(__doc__.strip())
        return 0

    map_arg, positionals = None, []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--map":
            if i + 1 >= len(argv):
                return refuse("--map takes a value")
            map_arg = argv[i + 1]
            i += 2
            continue
        positionals.append(arg)
        i += 1

    if len(positionals) != 1 or positionals[0] != ROLE:
        return refuse(f"refusing: only {ROLE!r} resolves here, and it takes "
                      "no address argument")

    map_path = Path(map_arg) if map_arg is not None else default_map()
    if map_path is None:
        return refuse("--map not given and no git repository found to "
                      "default it from")

    value = read_row(map_path, ROLE_KEY)
    if value is None:
        return refuse(f"{map_path}: no {ROLE_KEY!r} row inside its "
                      "```identity fence")

    print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
