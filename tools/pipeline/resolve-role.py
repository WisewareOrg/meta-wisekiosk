#!/usr/bin/env python3
"""Resolve a board role to its bare address from the site's identity map.

    resolve-role.py [--map <path>] bench

Only `bench` ever resolves (#119 decision 7): the pipeline runs unattended
under a systemd timer, where `.claude/hooks/guard.sh`'s prod protection does
not run -- this refusal IS the pipeline's own safety control against an
accidental OTA or reboot of the wall-mounted prod board. Any other role, no
role, or a role plus anything else on the command line is refused: rc 2,
nothing on stdout, the reason on stderr. There is no way to pass an address
directly -- the only inputs are a role name and which map to read it from.

--map defaults to <repo root>/local/device-identity.md, the repo root found
by `git rev-parse --show-toplevel` from the current directory.

The map's ```identity fence and `key = value` row format is owned by
tools/scrub-identity.py's module docstring; parsed fresh here rather than
imported, since that script's own loader is scoped to a git repo root and
every caller here already has an explicit --map path.

Exit 2: refused -- wrong role, no role, extra arguments, no --map file, or
        the map has no `bench.address` row. The reason is on stderr.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent

# Hyphenated filename, so it cannot be a normal import: loaded by path, only
# for its git_env(), which is the worktree-git-env guard -- a leaked
# GIT_DIR/GIT_INDEX_FILE from an enclosing worktree's hooks would send the
# --map default's `git rev-parse` at that worktree's repository instead of
# this one. Owned by tools/layer-currency.py; not duplicated here. Same
# technique as tools/artifact-diff.py.
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
