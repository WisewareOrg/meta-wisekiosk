#!/usr/bin/env python3
"""Resolve a board's role and hostname from local/device-identity.md.

    device-role.py <address>    -- print "role=<r> hostname=<h>", rc 1 on no match

The single definition `oe-test.sh` and `install.sh` both called inline before
this file existed. Scans the map's ```identity fence through
tools/scrub-identity.py's own fenced-block parser (loaded by path -- the file
name has a hyphen), never a copy of its regexes. Only "prod" and "bench" are
ever candidates; any other role's address is "no role has address X", the
same as an address matching no row at all.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

_SCRUB_IDENTITY = None


def _load_scrub_identity():
    """Load `tools/scrub-identity.py` by path and cache the module.

    Loaded by path, not imported, because the file name has a hyphen.

    Returns:
        module: The loaded `scrub-identity.py` module, cached across calls.
    """
    global _SCRUB_IDENTITY
    if _SCRUB_IDENTITY is None:
        tools = Path(__file__).resolve().parent
        spec = importlib.util.spec_from_file_location("scrub_identity", tools / "scrub-identity.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SCRUB_IDENTITY = module
    return _SCRUB_IDENTITY


def resolve_role(fence_text, address):
    """Resolve which role -- `prod` or `bench` only -- owns `address`.

    Scans `fence_text` through `tools/scrub-identity.py`'s own `_map_rows` fenced-block parser,
    never a copy of its regexes, for whichever of `prod`/`bench` has `<role>.address == address`.

    Args:
        fence_text (str): Text containing a ` ```identity ` fenced block, in
            `local/device-identity.md`'s own `key = value` shape.
        address (str): The address to resolve.

    Returns:
        tuple[str, str]: `(role, hostname)` -- `role` is `"prod"` or `"bench"`; `hostname` is that
        role's own `<role>.hostname` row, or `""` if the map carries none.

    Raises:
        ValueError: Naming `address`, when neither role's address matches it -- including when a
            well-formed row for some other role matches, since only `prod`/`bench` are candidates.
    """
    scrub_identity = _load_scrub_identity()
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(fence_text)
        temp_path = Path(f.name)
    try:
        rows = dict(scrub_identity._map_rows(temp_path))
    finally:
        temp_path.unlink()
    role = next((r for r in ("prod", "bench") if rows.get(f"{r}.address") == address), None)
    if role is None:
        raise ValueError(f"no role in the map has address {address}")
    return role, rows.get(f"{role}.hostname", "")


def main():
    """Parse argv, resolve the named address's role, and print `role=<r> hostname=<h>`.

    Returns:
        int: 0 on a resolved role; 1 if the map could not be read or no role matched the given
        address; 2 on bad usage (not exactly one argument).
    """
    if len(sys.argv) != 2:
        print("usage: device-role.py <address>", file=sys.stderr)
        return 2
    address = sys.argv[1]
    root = Path(__file__).resolve().parent.parent
    scrub_identity = _load_scrub_identity()
    map_file = scrub_identity.map_path(root)
    try:
        fence_text = map_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"device-role.py: cannot read {map_file}: {exc}", file=sys.stderr)
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
