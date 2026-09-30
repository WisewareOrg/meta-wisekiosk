#!/usr/bin/env python3
"""Self-test for tools/artifact-diff.py. Run by `just guards` and by CI.

    artifact-diff-test.py       -- every case

`artifact-diff.py [--repo <buildhistory dir>] <base-ref> <head-ref>` is the
empty-artifact-delta predicate (#119 D-C): inside a buildhistory git repo, find
the image dir by glob `images/*/*/core-image-base/` and `git diff` the three
files it records -- installed-package-versions.txt, files-in-image.txt,
image-info.txt -- between two refs. rc 0 + that diff on stdout when any of the
three differs; rc 1 + "no change in image" on stderr when none does; rc 2 +
"could not tell" plus the reason on stderr when the repo, a ref or the image
dir cannot be resolved, printing nothing on stdout.

Every fixture here is its own small git repository, built in a tempdir and
never this tree's own history: this repository is PUBLIC and the tool's job is
to run against buildhistory, not against meta-wisekiosk itself.
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ARTIFACT_DIFF = TOOLS / "artifact-diff.py"

# Loaded by path only for its git_env(): a fixture git call must not inherit
# GIT_DIR/GIT_INDEX_FILE from a pre-commit hook running in a linked worktree,
# or a fixture commit lands in the real repository instead of its own tmpdir.
sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


currency = load("layer-currency")

PASS, FAIL = [], []


def case(name, got, want):
    (PASS if got == want else FAIL).append(name)
    if got != want:
        print(f"FAIL  {name}\n        want {want!r}\n        got  {got!r}")


def clean_env(**overrides):
    return currency.git_env(
        GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@example.com",
        GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@example.com",
        **overrides)


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                    capture_output=True, text=True, env=clean_env())


def init_repo(where):
    repo = Path(where) / "buildhistory"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    return repo


# The MACHINE_ARCH form (`raspberrypi0-wifi` -> `raspberrypi0_wifi`) is the
# path segment throughout: an implementation that globbed on the literal
# hyphenated machine name would match nothing against any fixture here.
IMAGE_REL = "images/raspberrypi0_wifi/glibc/core-image-base"


def image_dir(repo, rel=IMAGE_REL):
    d = repo / rel
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_triple(d, pkgver="curl 8.7.1-r0\n",
                  files="/usr/bin/curl 0755 root root 229432\n",
                  info="IMAGE_BASENAME = core-image-base\n"):
    (d / "installed-package-versions.txt").write_text(pkgver)
    (d / "files-in-image.txt").write_text(files)
    (d / "image-info.txt").write_text(info)


def commit(repo, msg, tag=None):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         capture_output=True, text=True,
                         env=clean_env()).stdout.strip()
    if tag:
        git(repo, "tag", tag)
    return sha


def run_diff(repo, base, head, argv_repo=True):
    """One artifact-diff.py invocation, as a real subprocess."""
    argv = [sys.executable, str(ARTIFACT_DIFF)]
    if argv_repo:
        argv += ["--repo", str(repo)]
    argv += [base, head]
    return subprocess.run(argv, capture_output=True, text=True,
                          env=clean_env())


def real_diff(repo, base, head, rel=IMAGE_REL):
    """The independently-computed `git diff` of the three tracked files --
    what "rc 0 + the git diff of those files on stdout" means, taken literally
    and not re-derived through the tool under test."""
    return subprocess.run(
        ["git", "-C", str(repo), "diff", base, head, "--",
         f"{rel}/installed-package-versions.txt",
         f"{rel}/files-in-image.txt",
         f"{rel}/image-info.txt"],
        capture_output=True, text=True, env=clean_env()).stdout


# --- rc 1: no change in image ----------------------------------------------

def empty_delta_cases():
    with tempfile.TemporaryDirectory() as tmp:
        repo = init_repo(tmp)
        write_triple(image_dir(repo))
        base = commit(repo, "base", tag="baseline/aaaa")
        head = commit(repo, "head, no file changed")
        got = run_diff(repo, base, head)
    case("artifact-diff: no change in any of the three files exits 1",
         got.returncode, 1)
    case("artifact-diff: identical delta names it on stderr",
         "no change in image" in got.stderr, True)
    case("artifact-diff: identical delta prints nothing on stdout",
         got.stdout, "")

    # Decision 3 (size-blind): buildhistory's three files record package
    # versions and file mode/owner/size/path, never content. A packaged file
    # whose CONTENT changed at the same size, mode, owner and path leaves
    # files-in-image.txt byte-identical, so this reads as "no change" too --
    # the documented limit, not a bug this tool can see past.
    with tempfile.TemporaryDirectory() as tmp:
        repo = init_repo(tmp)
        write_triple(image_dir(repo),
                     files="/usr/bin/wisekiosk 0755 root root 4213112\n")
        base = commit(repo, "base")
        # The packaged file's bytes would differ in the real image; nothing
        # buildhistory records about it does, so the fixture is byte-identical.
        write_triple(image_dir(repo),
                     files="/usr/bin/wisekiosk 0755 root root 4213112\n")
        head = commit(repo, "same-size content change, unseen by buildhistory")
        got = run_diff(repo, base, head)
    case("artifact-diff: a same-size content change in a packaged file "
         "is NOT detected (decision 3, size-blind)", got.returncode, 1)
    case("artifact-diff: the size-blind case also names it on stderr",
         "no change in image" in got.stderr, True)


# --- rc 0: the git diff of the three files ---------------------------------

def changed_cases():
    # Package version bump: installed-package-versions.txt only.
    with tempfile.TemporaryDirectory() as tmp:
        repo = init_repo(tmp)
        write_triple(image_dir(repo), pkgver="curl 8.7.1-r0\n")
        base = commit(repo, "base")
        write_triple(image_dir(repo), pkgver="curl 8.9.0-r0\n")
        head = commit(repo, "bump curl")
        got = run_diff(repo, base, head)
        expected = real_diff(repo, base, head)
    case("artifact-diff: a package version bump exits 0", got.returncode, 0)
    case("artifact-diff: stdout is exactly `git diff` of the three files "
         "(package bump)", got.stdout, expected)

    # File-list change only: files-in-image.txt.
    with tempfile.TemporaryDirectory() as tmp:
        repo = init_repo(tmp)
        write_triple(image_dir(repo),
                     files="/usr/bin/curl 0755 root root 229432\n")
        base = commit(repo, "base")
        write_triple(image_dir(repo),
                     files="/usr/bin/curl 0755 root root 229432\n"
                           "/usr/bin/wisekiosk 0755 root root 4213112\n")
        head = commit(repo, "add a file")
        got = run_diff(repo, base, head)
        expected = real_diff(repo, base, head)
    case("artifact-diff: a file-list-only change exits 0", got.returncode, 0)
    case("artifact-diff: stdout is exactly `git diff` of the three files "
         "(file-list change)", got.stdout, expected)

    # image-info.txt change only.
    with tempfile.TemporaryDirectory() as tmp:
        repo = init_repo(tmp)
        write_triple(image_dir(repo),
                     info="IMAGE_BASENAME = core-image-base\n"
                          "DISTRO_VERSION = 1.0\n")
        base = commit(repo, "base")
        write_triple(image_dir(repo),
                     info="IMAGE_BASENAME = core-image-base\n"
                          "DISTRO_VERSION = 1.1\n")
        head = commit(repo, "bump distro version")
        got = run_diff(repo, base, head)
        expected = real_diff(repo, base, head)
    case("artifact-diff: an image-info-only change exits 0", got.returncode, 0)
    case("artifact-diff: stdout is exactly `git diff` of the three files "
         "(image-info change)", got.stdout, expected)


# --- rc 2: could not tell ---------------------------------------------------

def could_not_tell_cases():
    # Missing image dir: the glob matches nothing.
    with tempfile.TemporaryDirectory() as tmp:
        repo = init_repo(tmp)
        (repo / "conf").mkdir()
        (repo / "conf" / "placeholder").write_text("nothing image-shaped here\n")
        base = commit(repo, "base")
        head = commit(repo, "head")
        got = run_diff(repo, base, head)
    case("artifact-diff: no matching image dir exits 2", got.returncode, 2)
    case("artifact-diff: no matching image dir prints nothing on stdout",
         got.stdout, "")
    case("artifact-diff: no matching image dir says could not tell",
         "could not tell" in got.stderr, True)

    # Ambiguous image dir: the glob matches more than one.
    with tempfile.TemporaryDirectory() as tmp:
        repo = init_repo(tmp)
        write_triple(image_dir(repo, "images/raspberrypi0_wifi/glibc/core-image-base"))
        write_triple(image_dir(repo, "images/raspberrypi4_64/glibc/core-image-base"))
        base = commit(repo, "base")
        head = commit(repo, "head")
        got = run_diff(repo, base, head)
    case("artifact-diff: two matching image dirs exits 2", got.returncode, 2)
    case("artifact-diff: two matching image dirs prints nothing on stdout",
         got.stdout, "")
    case("artifact-diff: two matching image dirs says could not tell",
         "could not tell" in got.stderr, True)

    # Unknown ref, in each position.
    with tempfile.TemporaryDirectory() as tmp:
        repo = init_repo(tmp)
        write_triple(image_dir(repo))
        base = commit(repo, "base")
        head = commit(repo, "head")
        bad_base = run_diff(repo, "no-such-ref", head)
        bad_head = run_diff(repo, base, "no-such-ref")
    case("artifact-diff: an unresolvable base-ref exits 2",
         bad_base.returncode, 2)
    case("artifact-diff: an unresolvable base-ref prints nothing on stdout",
         bad_base.stdout, "")
    case("artifact-diff: an unresolvable base-ref says could not tell",
         "could not tell" in bad_base.stderr, True)
    case("artifact-diff: an unresolvable head-ref exits 2",
         bad_head.returncode, 2)
    case("artifact-diff: an unresolvable head-ref prints nothing on stdout",
         bad_head.stdout, "")
    case("artifact-diff: an unresolvable head-ref says could not tell",
         "could not tell" in bad_head.stderr, True)

    # Not a git repo at all.
    with tempfile.TemporaryDirectory() as tmp:
        not_a_repo = Path(tmp) / "not-a-repo"
        not_a_repo.mkdir()
        (not_a_repo / "images").mkdir()
        got = run_diff(not_a_repo, "a", "b")
    case("artifact-diff: --repo pointing at a non-git directory exits 2",
         got.returncode, 2)
    case("artifact-diff: a non-git --repo prints nothing on stdout",
         got.stdout, "")
    case("artifact-diff: a non-git --repo says could not tell",
         "could not tell" in got.stderr, True)


# --- --repo defaults to build/buildhistory ---------------------------------

def default_repo_cases():
    with tempfile.TemporaryDirectory() as tmp:
        top = Path(tmp)
        repo = top / "build" / "buildhistory"
        repo.mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")
        write_triple(image_dir(repo), pkgver="curl 8.7.1-r0\n")
        base = commit(repo, "base")
        write_triple(image_dir(repo), pkgver="curl 8.9.0-r0\n")
        head = commit(repo, "bump curl")
        got = subprocess.run([sys.executable, str(ARTIFACT_DIFF), base, head],
                             cwd=str(top), capture_output=True, text=True,
                             env=clean_env())
        expected = real_diff(repo, base, head)
    case("artifact-diff: --repo omitted defaults to build/buildhistory "
         "under the cwd", got.returncode, 0)
    case("artifact-diff: the default-repo run reads the same diff as an "
         "explicit --repo would", got.stdout, expected)


# --- --help ------------------------------------------------------------

def help_cases():
    got = subprocess.run([sys.executable, str(ARTIFACT_DIFF), "--help"],
                         capture_output=True, text=True, env=clean_env())
    case("artifact-diff: --help exits 0", got.returncode, 0)
    case("artifact-diff: --help names the rc-1 case by its own wording",
         "no change in image" in got.stdout, True)
    case("artifact-diff: --help names the rc-2 case by its own wording",
         "could not tell" in got.stdout, True)
    case("artifact-diff: --help mentions exit code 0",
         "0" in got.stdout, True)


def main() -> int:
    empty_delta_cases()
    changed_cases()
    could_not_tell_cases()
    default_repo_cases()
    help_cases()
    print(f"\npass={len(PASS)} fail={len(FAIL)} skip=0")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
