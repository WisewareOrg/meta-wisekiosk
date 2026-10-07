#!/usr/bin/env python3
"""Check every local item citing an upstream WiseKiosk obligation against the
upstream tree at the pinned `SRCREV`. See docs/requirements/README.md.

    upstream-reqs-check.py

`read_srcrev`, `parse_citation` and `compare` are pure; `fetch_upstream_item`
(`gh api`) and `find_cited_items` (the local tree walk) are not -- see
tools/upstream-reqs-check-test.py.
"""
import base64
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

UPSTREAM_OWNER = "WisewareOrg"
SRC_INC = Path("meta-wisekiosk/recipes-wisekiosk/wisekiosk/wisekiosk-src.inc")
REQS_ROOT = Path("docs/requirements")

SRCREV_LINE = re.compile(r'(?m)^SRCREV\s*=\s*"([^"]*)"')
CITATION_LINE = re.compile(r'(?m)^(\S+)\s+([A-Z]{2,5}[0-9]+)\s+(.+?)\s*$')

TIER_PREFIX = {"sys": "SYS", "srs": "SRS", "tst": "TST"}


def read_srcrev(inc_text: str) -> str:
    """The `SRCREV` this tree's WiseKiosk pin resolves to."""
    match = SRCREV_LINE.search(inc_text)
    if not match:
        raise ValueError("no SRCREV line found")
    return match.group(1)


def parse_citation(rationale_text: str):
    """Every `<repo> <item id> <header>` citation line in a `rationale` string."""
    return [(m.group(1), m.group(2), m.group(3)) for m in CITATION_LINE.finditer(rationale_text)]


def compare(cited_header, cited_reviewed, upstream_item):
    """Mismatches between a citation (`header`, `upstream-reviewed`) and the fetched upstream
    item (`{"header": ..., "reviewed": ...}`, or None when the cited id does not exist upstream).
    Empty list means everything matches."""
    if upstream_item is None:
        return ["cited upstream item not found"]
    problems = []
    if upstream_item.get("header") != cited_header:
        problems.append(
            f"header differs: cited {cited_header!r}, upstream is now {upstream_item.get('header')!r}"
        )
    if upstream_item.get("reviewed") != cited_reviewed:
        problems.append(
            f"reviewed differs: recorded {cited_reviewed!r}, upstream is now {upstream_item.get('reviewed')!r}"
        )
    return problems


class UpstreamFetchError(RuntimeError):
    """`gh api` failed for a reason other than the cited item not existing upstream."""


def classify_gh_failure(returncode: int, stderr: str) -> str:
    """What a nonzero `gh api` exit means: `"auth"` (gh's own exit code for no credential),
    `"not-found"` (the cited item does not exist upstream, an HTTP 404), or `"other"` (network,
    rate limit, or an unexpected API error)."""
    if returncode == 4:
        return "auth"
    if "HTTP 404" in stderr:
        return "not-found"
    return "other"


def fetch_upstream_item(repo: str, item_id: str, ref: str):
    """The upstream item's `header` and `reviewed` fields at `ref`, or None if it has none.

    :raises UpstreamFetchError: `gh api` failed for any reason other than the item not existing.
    """
    prefix = re.match(r"[A-Z]+", item_id).group(0)
    tier = {v: k for k, v in TIER_PREFIX.items()}.get(prefix)
    if tier is None:
        return None
    path = f"docs/requirements/{tier}/{item_id}.yml"
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{UPSTREAM_OWNER}/{repo}/contents/{path}?ref={ref}", "--jq", ".content"],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpstreamFetchError(f"gh api timed out: {exc}") from exc
    except FileNotFoundError as exc:
        raise UpstreamFetchError(f"gh is not installed or not on PATH: {exc}") from exc
    if out.returncode != 0:
        kind = classify_gh_failure(out.returncode, out.stderr)
        if kind == "not-found":
            return None
        raise UpstreamFetchError(f"gh api failed ({kind}): {out.stderr.strip()}")
    content = base64.b64decode(out.stdout.strip()).decode("utf-8")
    item = yaml.safe_load(content) or {}
    return {"header": (item.get("header") or "").strip(), "reviewed": item.get("reviewed")}


def find_cited_items(root: Path):
    """Every (citing uid, repo, item id, cited header, recorded reviewed stamp) under `root`."""
    found = []
    for tier in sorted(TIER_PREFIX):
        for path in sorted((root / tier).glob("*.yml")):
            if path.stem.startswith("."):
                continue
            item = yaml.safe_load(path.read_text()) or {}
            rationale = item.get("rationale") or ""
            recorded = item.get("upstream-reviewed")
            for repo, item_id, header in parse_citation(rationale):
                found.append((path.stem, repo, item_id, header, recorded))
    return found


def main() -> int:
    if yaml is None:
        print("upstream-reqs-check: PyYAML is required", file=sys.stderr)
        return 1

    srcrev = read_srcrev(SRC_INC.read_text())
    citations = find_cited_items(REQS_ROOT)

    if not citations:
        print(f"0 item(s) cite an upstream obligation (checked against {UPSTREAM_OWNER}/WiseKiosk@{srcrev}).")
        return 0

    failures = []
    fetch_errors = []
    for uid, repo, item_id, header, recorded in citations:
        try:
            upstream_item = fetch_upstream_item(repo, item_id, srcrev)
        except UpstreamFetchError as exc:
            fetch_errors.append((uid, repo, item_id, str(exc)))
            continue
        problems = compare(header, recorded, upstream_item)
        if problems:
            failures.append((uid, repo, item_id, problems))

    if fetch_errors:
        print(f"{len(fetch_errors)} locally-cited item(s) could not be checked against upstream:",
              file=sys.stderr)
        for uid, repo, item_id, message in fetch_errors:
            print(f"  {uid} cites {repo} {item_id}: {message}", file=sys.stderr)
        return 1

    if failures:
        print(f"{len(failures)} locally-cited item(s) no longer match upstream:", file=sys.stderr)
        for uid, repo, item_id, problems in failures:
            print(f"  {uid} cites {repo} {item_id}:", file=sys.stderr)
            for problem in problems:
                print(f"    {problem}", file=sys.stderr)
        print("\nRe-review the local item against the upstream change.", file=sys.stderr)
        return 1

    print(f"{len(citations)} locally-cited item(s) checked against {UPSTREAM_OWNER}/WiseKiosk@{srcrev}: all match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
