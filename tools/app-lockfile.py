#!/usr/bin/env python3
"""Write the app's npm shrinkwrap from its own lockfile at the pinned commit.

    app-lockfile.py -- write wisekiosk-frontend/npm-shrinkwrap.json
                        (gitignored, build input)

The shrinkwrap has to be byte-for-byte what the app's own CI locked, not
`npm`-regenerated here, so this fetches frontend/package-lock.json straight
from the pinned commit rather than running npm at all. A gitignored
`<shrinkwrap>.srcrev` stamp beside it records which commit it is for, so a
build entry point that runs this on every invocation skips the fetch once
it is already current.

`fetch_lockfile(url, srcrev) -> bytes` is the only network-touching
function; it and `is_current`/`write_shrinkwrap` are the importable seams
for tests.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent

# Where the pin and the git URL come from -- one file, shared with
# tools/go-mods.py's own parse of it.
SRC_INC = ROOT / "meta-wisekiosk/recipes-wisekiosk/wisekiosk/wisekiosk-src.inc"

# Written at build entry, never committed -- npmsw:// in
# wisekiosk-frontend_git.bb fetches this path.
SHRINKWRAP_PATH = (ROOT / "meta-wisekiosk/recipes-wisekiosk/wisekiosk/"
                   "wisekiosk-frontend/npm-shrinkwrap.json")

LOCKFILE_PATH_IN_REPO = "frontend/package-lock.json"


def refuse(message: str) -> int:
    print(f"{message} -- refusing to report a pass", file=sys.stderr)
    return 2


def _src_inc_fields(src_inc: Path = SRC_INC):
    """(url, srcrev) as bitbake reads them from wisekiosk-src.inc -- the same
    parse tools/go-mods.py does, kept separate rather than shared so neither
    tool depends on the other. `src_inc` is the importable seam for tests, a
    fixture file in place of the real one."""
    text = src_inc.read_text()
    srcrev = re.search(r'^SRCREV\s*=\s*"([0-9a-f]{40})"', text, re.M).group(1)
    src_uri = re.search(r'^SRC_URI\s*=\s*"([^"]+)"', text, re.M).group(1)
    scheme_and_path, *params = src_uri.split(";")
    protocol = next((p.split("=", 1)[1] for p in params
                      if p.startswith("protocol=")), None)
    _, _, rest = scheme_and_path.partition("://")
    return f"{protocol or 'https'}://{rest}", srcrev


def _raw_url(url: str, srcrev: str) -> str:
    """The raw.githubusercontent.com URL for frontend/package-lock.json at
    srcrev, derived from the git clone URL wisekiosk-src.inc names."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if not m:
        raise ValueError(f"not a github.com clone URL: {url}")
    owner, repo = m.groups()
    return (f"https://raw.githubusercontent.com/{owner}/{repo}/{srcrev}/"
            f"{LOCKFILE_PATH_IN_REPO}")


def fetch_lockfile(url: str, srcrev: str) -> bytes:
    """The pinned commit's own frontend/package-lock.json, verbatim."""
    try:
        with urllib.request.urlopen(_raw_url(url, srcrev)) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        sys.exit(refuse(f"{exc.geturl()}: HTTP {exc.code}"))


def stamp_path_for(path: Path) -> Path:
    """The gitignored stamp file recording which SRCREV `path` was written
    for, beside it."""
    return path.with_name(path.name + ".srcrev")


def is_current(srcrev: str, path: Path = SHRINKWRAP_PATH) -> bool:
    """True when `path` already holds this srcrev's content, per its stamp --
    both the file and its stamp must exist, and the stamp must match. The
    importable seam for "skip when current" tests."""
    stamp = stamp_path_for(path)
    return (path.exists() and stamp.exists()
            and stamp.read_text().strip() == srcrev)


def write_shrinkwrap(content: bytes, srcrev: str, path: Path = SHRINKWRAP_PATH) -> int:
    """Validate `content` is JSON and write it verbatim to `path`
    (atomically), refusing (no write, no stamp) on invalid JSON. The old
    stamp is removed before the replace, not just rewritten after: an
    interrupt between a successful replace and the stamp write must never
    leave a stamp claiming content it did not write, so the safe failure
    mode is no stamp at all (is_current() then reads as stale, not
    current). The importable seam for tests, alongside fetch_lockfile."""
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        return refuse(f"fetched content is not valid JSON: {exc}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(content)
    stamp = stamp_path_for(path)
    stamp.unlink(missing_ok=True)
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    stamp.write_text(srcrev)
    return 0


def main() -> int:
    if sys.argv[1:]:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2

    url, srcrev = _src_inc_fields()
    if is_current(srcrev):
        return 0

    content = fetch_lockfile(url, srcrev)
    return write_shrinkwrap(content, srcrev)


if __name__ == "__main__":
    sys.exit(main())
