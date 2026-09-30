#!/usr/bin/env python3
"""Report whether a buildhistory image directory differs between two refs.

    artifact-diff.py [--repo <buildhistory dir>] <base-ref> <head-ref>

Inside a buildhistory git repository, the image directory is found by glob
`images/*/*/core-image-base/` -- exactly one match is required, since the
MACHINE_ARCH path segment swaps `-` for `_` (raspberrypi0-wifi ->
raspberrypi0_wifi) and a literal machine name would silently match nothing.
The three files buildhistory records there -- installed-package-versions.txt,
files-in-image.txt, image-info.txt -- are compared between base-ref and
head-ref with `git diff`. `buildhistory-diff` is not used: it needs
GitPython, which this tree does not carry.

Exit 0: at least one of the three files differs between the refs. The `git
        diff` of all three is printed on stdout.
Exit 1: none of the three files differs. "no change in image" is printed on
        stderr and nothing is printed on stdout -- a pipeline failure, not a
        skip (#119 epic: automated build-and-test pipeline). The predicate
        is size-blind by design (#121 artifact delta tier).
Exit 2: the repo, a ref, or the image directory could not be resolved. The
        reason is printed on stderr, prefixed "could not tell", and nothing
        is printed on stdout.

--repo defaults to build/buildhistory under the current directory.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent

# Hyphenated filename, so it cannot be a normal import: loaded by path, only
# for its git_env(), which is the worktree-git-env guard -- a leaked
# GIT_DIR/GIT_INDEX_FILE from an enclosing worktree's hooks would send every
# git call below at that worktree's repository instead of --repo. Owned by
# tools/layer-currency.py; not duplicated here.
_spec = importlib.util.spec_from_file_location(
    "layer_currency", TOOLS / "layer-currency.py")
_layer_currency = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_layer_currency)
git_env = _layer_currency.git_env

# The three files buildhistory writes into the image directory on every
# build. This order does not affect `git diff`'s own output order, which is
# by path, not by pathspec argument order.
TRACKED = ("installed-package-versions.txt", "files-in-image.txt",
           "image-info.txt")

# MACHINE_ARCH swaps `-` -> `_` in this path segment; a literal machine name
# would silently match nothing.
IMAGE_GLOB = "images/*/*/core-image-base"

DEFAULT_REPO = Path("build/buildhistory")

COULD_NOT_TELL = "could not tell"


def git(repo, *args):
    """One git invocation in `repo`, as a CompletedProcess."""
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, env=git_env())


def refuse(reason):
    print(f"{COULD_NOT_TELL}: {reason}", file=sys.stderr)
    return 2


def image_dir(repo):
    """The one `images/*/*/core-image-base` directory in `repo`, or None."""
    matches = sorted(p for p in Path(repo).glob(IMAGE_GLOB) if p.is_dir())
    return matches[0] if len(matches) == 1 else None


def parse_args(argv):
    """(repo, base-ref, head-ref), or None on a malformed invocation."""
    repo = DEFAULT_REPO
    rest = list(argv)
    if rest[:1] == ["--repo"]:
        if len(rest) < 2:
            return None
        repo, rest = Path(rest[1]), rest[2:]
    if len(rest) != 2:
        return None
    return repo, rest[0], rest[1]


def main() -> int:
    argv = sys.argv[1:]
    if argv == ["--help"]:
        print(__doc__.strip())
        return 0

    parsed = parse_args(argv)
    if parsed is None:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    repo, base, head = parsed

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
