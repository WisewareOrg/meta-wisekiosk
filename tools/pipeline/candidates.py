#!/usr/bin/env python3
"""Print the next pipeline job, or nothing.

    candidates.py

No arguments -- every input comes from the environment: PIPELINE_BASELINE_REF,
PIPELINE_TREE, KAS_BUILD_DIR. PIPELINE_BASELINE_REF is a full ref, already
qualified with its remote (e.g. `origin/main`) -- not a bare branch name.
Prints one line, `<kind> <sha> [<pr>]`, or nothing when there is no candidate
ready. `git fetch origin` is run in PIPELINE_TREE first, so every ref below
is current.

Order, one job per tick:

  1. `$PIPELINE_BASELINE_REF`'s HEAD, if its tree carries the pipeline
     overlays, it has no `baseline/<sha>` tag in `$KAS_BUILD_DIR/buildhistory`,
     and it has no live `bench-pipeline` status -> `baseline <sha>`.
  2. Every open PR whose head is in THIS repository (never a fork), oldest
     first, whose diff against `merge-base(baseline ref, head)` touches an
     image input (`includes/**`, `meta-wisekiosk/**`, `kiosk-zero-w.yaml`,
     `patches/**`) and whose head tree carries the pipeline overlays
     (`includes/buildhistory.yaml`, `includes/testimage.yaml`,
     `meta-wisekiosk/lib/oeqa/runtime/cases/wisekiosk.py`) -- drafts included:
       - its merge-base's tree carries the pipeline overlays, has no
         `baseline/<sha>` tag, and no live status -> `baseline <merge-base>`;
         a merge-base without the overlays, or with a live status already
         (a prior attempt not yet tagged), skips the PR instead of
         re-emitting it
       - its head equals its merge-base -> skip, the baseline run covers it
       - its head has no live `bench-pipeline` status -> `pr <head-sha> <number>`

A status counts as live unless it is missing, or is `pending` and older than
6 hours; a `gh` failure while checking also counts as live (fails closed). A
`git fetch` failure exits non-zero.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

STALE_PENDING_HOURS = 6
CONTEXT = "bench-pipeline"
REPO_OWNER = "tjwise99"

IMAGE_INPUT_PREFIXES = ("includes/", "meta-wisekiosk/", "patches/")
IMAGE_INPUT_FILES = ("kiosk-zero-w.yaml",)

OVERLAY_PATHS = (
    "includes/buildhistory.yaml",
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
    return all(git(tree, "cat-file", "-e", f"{sha}:{path}").returncode == 0
              for path in OVERLAY_PATHS)


def has_baseline_tag(build_dir, sha):
    result = git(f"{build_dir}/buildhistory", "tag", "-l", f"baseline/{sha}")
    return result.returncode == 0 and result.stdout.strip() != ""


def live_status(sha):
    """True if `sha` already has a non-stale bench-pipeline status, or if
    that cannot be determined -- a gh failure fails closed (skip), not
    open (re-trigger a build)."""
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
         "number,headRefOid,headRefName,isDraft,headRepositoryOwner,"
         "baseRefName,createdAt"],
        capture_output=True, text=True)
    if result.returncode != 0:
        return []
    prs = json.loads(result.stdout)
    prs = [p for p in prs
          if (p.get("headRepositoryOwner") or {}).get("login") == REPO_OWNER]
    prs.sort(key=lambda p: p.get("createdAt", ""))
    return prs


def main():
    if sys.argv[1:] == ["--help"]:
        print(__doc__.strip())
        return 0

    baseline_remote = env("PIPELINE_BASELINE_REF")
    tree = env("PIPELINE_TREE")
    build_dir = env("KAS_BUILD_DIR")

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
