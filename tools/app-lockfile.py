#!/usr/bin/env python3
"""Write the app's npm shrinkwrap from its own lockfile at the pinned commit.

    app-lockfile.py -- write wisekiosk-frontend/npm-shrinkwrap.json
                        (gitignored, build input)

The shrinkwrap has to be byte-for-byte what the app's own CI locked, not
`npm`-regenerated here, so this fetches frontend/package-lock.json straight
from the pinned commit rather than running npm at all.

`fetch_lockfile(url, srcrev) -> bytes` is the only network-touching function,
and the importable seam for tests.
"""
import json
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


def _src_inc_fields():
    """(url, srcrev) as bitbake reads them from wisekiosk-src.inc -- the same
    parse tools/go-mods.py does, kept separate rather than shared so neither
    tool depends on the other."""
    text = SRC_INC.read_text()
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


def main() -> int:
    if sys.argv[1:]:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2

    url, srcrev = _src_inc_fields()
    content = fetch_lockfile(url, srcrev)
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        return refuse(f"fetched content is not valid JSON: {exc}")

    SHRINKWRAP_PATH.write_bytes(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
