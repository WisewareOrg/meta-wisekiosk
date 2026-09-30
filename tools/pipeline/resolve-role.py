#!/usr/bin/env python3
"""Resolve a board role to its bare address from the site's identity map.

    resolve-role.py [--map <path>] bench
    resolve-role.py [--map <path>] --verify-hostname <observed>

Only `bench` resolves. Any other role, no role, extra arguments, a missing
--map file, a map with no `bench.address` row, or a map where bench.address
equals another role's `*.address` row: rc 2, nothing on stdout, the reason
on stderr.

--verify-hostname takes no role argument: rc 0 if <observed> equals the
map's `bench.hostname` row and no other `*.hostname` row; rc 2 otherwise
(missing bench.hostname row included).

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
ROLE_HOSTNAME_KEY = "bench.hostname"

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


def read_all_rows(map_path):
    """[(key, value), ...] for every row inside map_path's ```identity
    fence, or None if the map cannot be read."""
    try:
        text = map_path.read_text(encoding="utf-8")
    except OSError:
        return None
    rows, inside = [], False
    for line in text.splitlines():
        if not inside:
            if FENCE_OPEN.match(line):
                inside = True
            continue
        if FENCE_CLOSE.match(line):
            break
        m = MAP_ROW.match(line)
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


def read_row(map_path, key):
    """The value of `key` inside map_path's ```identity fence, or None."""
    rows = read_all_rows(map_path)
    if rows is None:
        return None
    for row_key, value in rows:
        if row_key == key:
            return value
    return None


def resolve_map(map_arg):
    """The map path to use, or None with no repo found to default it from."""
    return Path(map_arg) if map_arg is not None else default_map()


def verify_hostname(map_path, observed):
    """0 if `observed` is bench's own hostname and no other role's; 2
    otherwise, with the reason on stderr."""
    rows = read_all_rows(map_path)
    if rows is None:
        return refuse(f"{map_path}: could not read the map")
    bench_hostname = next((v for k, v in rows if k == ROLE_HOSTNAME_KEY), None)
    if bench_hostname is None:
        return refuse(f"{map_path}: no {ROLE_HOSTNAME_KEY!r} row inside its "
                      "```identity fence")
    if observed != bench_hostname:
        return refuse(f"observed hostname {observed!r} does not match "
                      f"{ROLE_HOSTNAME_KEY} {bench_hostname!r}")
    for key, value in rows:
        if key.endswith(".hostname") and key != ROLE_HOSTNAME_KEY and value == observed:
            return refuse(f"observed hostname {observed!r} also matches "
                          f"{key!r} -- refusing")
    return 0


def main():
    argv = sys.argv[1:]
    if argv == ["--help"]:
        print(__doc__.strip())
        return 0

    map_arg, hostname_arg, positionals = None, None, []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--map":
            if i + 1 >= len(argv):
                return refuse("--map takes a value")
            map_arg = argv[i + 1]
            i += 2
            continue
        if arg == "--verify-hostname":
            if i + 1 >= len(argv):
                return refuse("--verify-hostname takes a value")
            hostname_arg = argv[i + 1]
            i += 2
            continue
        positionals.append(arg)
        i += 1

    if hostname_arg is not None:
        if positionals:
            return refuse("--verify-hostname takes no role argument")
        map_path = resolve_map(map_arg)
        if map_path is None:
            return refuse("--map not given and no git repository found to "
                          "default it from")
        return verify_hostname(map_path, hostname_arg)

    if len(positionals) != 1 or positionals[0] != ROLE:
        return refuse(f"refusing: only {ROLE!r} resolves here, and it takes "
                      "no address argument")

    map_path = resolve_map(map_arg)
    if map_path is None:
        return refuse("--map not given and no git repository found to "
                      "default it from")

    value = read_row(map_path, ROLE_KEY)
    if value is None:
        return refuse(f"{map_path}: no {ROLE_KEY!r} row inside its "
                      "```identity fence")

    rows = read_all_rows(map_path) or []
    for key, other in rows:
        if key.endswith(".address") and key != ROLE_KEY and other == value:
            return refuse(f"{ROLE_KEY} equals {key!r} -- refusing")

    print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
