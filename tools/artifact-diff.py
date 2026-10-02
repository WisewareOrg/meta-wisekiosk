#!/usr/bin/env python3
"""Diff two refs' buildhistory image directories.

    artifact-diff.py [--repo <buildhistory dir>] <base-ref> <head-ref>

Exit 0: at least one of the three files differs between the refs. The `git
        diff` of all three is printed on stdout.
Exit 1: none of the tracked files differs; "no change in image" on stderr.
Exit 2: the repo, a ref, or the image directory could not be resolved;
        "could not tell: <reason>" on stderr.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

TRACKED = ("installed-package-versions.txt", "files-in-image.txt",
           "image-info.txt")

# images/${MACHINE_ARCH}/${TCLIBC}/${IMAGE_BASENAME}
IMAGE_GLOB = "images/*/*/core-image-base"

DEFAULT_REPO = Path("build/buildhistory")

COULD_NOT_TELL = "could not tell"


def git(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, env=env)


def refuse(reason):
    print(f"{COULD_NOT_TELL}: {reason}", file=sys.stderr)
    return 2


def image_dir(repo):
    matches = sorted(p for p in Path(repo).glob(IMAGE_GLOB) if p.is_dir())
    return matches[0] if len(matches) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("base")
    parser.add_argument("head")
    args = parser.parse_args()
    repo, base, head = args.repo, args.base, args.head

    if git(repo, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return refuse(f"{repo} is not a git repository")

    for label, ref in (("base-ref", base), ("head-ref", head)):
        if git(repo, "rev-parse", "--verify", "-q",
              f"{ref}^{{commit}}").returncode != 0:
            return refuse(f"{label} {ref!r} does not resolve in {repo}")

    found = image_dir(repo)
    if found is None:
        return refuse(f"{IMAGE_GLOB} matched zero or more than one "
                      f"directory under {repo}")

    paths = [str(found.relative_to(repo) / name) for name in TRACKED]

    quiet = git(repo, "diff", "--quiet", base, head, "--", *paths)
    if quiet.returncode == 0:
        print("no change in image", file=sys.stderr)
        return 1
    if quiet.returncode != 1:
        return refuse(f"`git diff --quiet {base} {head}` failed in {repo}")

    diff = git(repo, "diff", base, head, "--", *paths)
    sys.stdout.write(diff.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
