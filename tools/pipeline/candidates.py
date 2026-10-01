#!/usr/bin/env python3
"""Print the next pipeline job, or nothing.

    candidates.py

Reads PIPELINE_BASELINE_REF (remote-qualified, e.g. origin/main) and
PIPELINE_TREE. Prints `<kind> <sha> [<pr>]`, or nothing with no candidate.
rc 0 either way; rc 1 if a variable is unset or `git fetch origin` fails.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

STALE_PENDING_HOURS = 6
CONTEXT = "bench-pipeline"

IMAGE_INPUT_PREFIXES = ("includes/", "meta-wisekiosk/", "patches/")
IMAGE_INPUT_FILES = ("kiosk-zero-w.yaml",)

OVERLAY_PATHS = (
    "includes/testimage.yaml",
    "meta-wisekiosk/lib/oeqa/runtime/cases/wisekiosk.py",
)


def env(name):
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"candidates.py: ${name} is not set")
    return value


def git(tree, *args):
    return subprocess.run(["git", "-C", tree, *args],
                          capture_output=True, text=True)


def touches_image_input(tree, base, head):
    diff = git(tree, "diff", "--name-only", f"{base}..{head}")
    if diff.returncode != 0:
        return False
    names = diff.stdout.splitlines()
    return any(n.startswith(IMAGE_INPUT_PREFIXES) or n in IMAGE_INPUT_FILES
              for n in names)


def carries_overlays(tree, sha):
    kas_config = git(tree, "show", f"{sha}:kiosk-zero-w.yaml")
    if kas_config.returncode != 0 or 'INHERIT += "buildhistory"' not in kas_config.stdout:
        return False
    return all(git(tree, "cat-file", "-e", f"{sha}:{path}").returncode == 0
              for path in OVERLAY_PATHS)


def has_baseline_tag(build_dir, sha):
    result = git(f"{build_dir}/buildhistory", "tag", "-l", f"baseline/{sha}")
    return result.returncode == 0 and result.stdout.strip() != ""


def live_status(sha):
    """True if `sha` has a bench-pipeline status other than a stale pending,
    or if gh or its output fails."""
    result = subprocess.run(
        ["gh", "api", f"repos/:owner/:repo/commits/{sha}/statuses"],
        capture_output=True, text=True)
    if result.returncode != 0:
        return True
    try:
        statuses = json.loads(result.stdout)
    except json.JSONDecodeError:
        return True
    for status in statuses:
        if status.get("context") != CONTEXT:
            continue
        if status.get("state") != "pending":
            return True
        created = status.get("created_at")
        if not created:
            return True
        age = datetime.now(timezone.utc) - datetime.fromisoformat(
            created.replace("Z", "+00:00"))
        if age < timedelta(hours=STALE_PENDING_HOURS):
            return True
    return False


def open_prs():
    """Open PRs, this repository's own heads only, oldest first."""
    result = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--limit", "200", "--json",
         "number,headRefOid,headRefName,isDraft,isCrossRepository,"
         "baseRefName,createdAt"],
        capture_output=True, text=True)
    if result.returncode != 0:
        return []
    prs = json.loads(result.stdout)
    prs = [p for p in prs if p.get("isCrossRepository") is False]
    prs.sort(key=lambda p: p.get("createdAt", ""))
    return prs


def main():
    if sys.argv[1:] == ["--help"]:
        print(__doc__.strip())
        return 0

    baseline_remote = env("PIPELINE_BASELINE_REF")
    tree = env("PIPELINE_TREE")
    build_dir = f"{tree}/build"

    fetch = git(tree, "fetch", "origin")
    if fetch.returncode != 0:
        sys.exit(f"candidates.py: git fetch origin failed in {tree}: "
                 f"{fetch.stderr.strip()}")

    head_sha = git(tree, "rev-parse", baseline_remote)
    if head_sha.returncode == 0:
        sha = head_sha.stdout.strip()
        if (carries_overlays(tree, sha) and not has_baseline_tag(build_dir, sha)
                and not live_status(sha)):
            print(f"baseline {sha}")
            return 0

    for pr in open_prs():
        head, number = pr.get("headRefOid"), pr.get("number")
        if not head or number is None:
            continue
        merge_base = git(tree, "merge-base", baseline_remote, head)
        if merge_base.returncode != 0:
            continue
        base = merge_base.stdout.strip()

        if not touches_image_input(tree, base, head):
            continue
        if not carries_overlays(tree, head):
            continue

        if not has_baseline_tag(build_dir, base):
            if carries_overlays(tree, base) and not live_status(base):
                print(f"baseline {base}")
                return 0
            continue
        if head == base:
            continue
        if not live_status(head):
            print(f"pr {head} {number}")
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
