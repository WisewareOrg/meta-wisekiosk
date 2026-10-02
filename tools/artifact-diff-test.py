#!/usr/bin/env python3
"""Self-test for tools/artifact-diff.py. Run as `python3 tools/artifact-diff-test.py`."""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ARTIFACT_DIFF = TOOLS / "artifact-diff.py"

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
    argv = [sys.executable, str(ARTIFACT_DIFF)]
    if argv_repo:
        argv += ["--repo", str(repo)]
    argv += [base, head]
    return subprocess.run(argv, capture_output=True, text=True,
                          env=clean_env())


def real_diff(repo, base, head, rel=IMAGE_REL):
    return subprocess.run(
        ["git", "-C", str(repo), "diff", base, head, "--",
         f"{rel}/installed-package-versions.txt",
         f"{rel}/files-in-image.txt",
         f"{rel}/image-info.txt"],
        capture_output=True, text=True, env=clean_env()).stdout


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


def changed_cases():
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


def could_not_tell_cases():
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
    case("artifact-diff: an unresolvable head-ref exits 2",
         bad_head.returncode, 2)
    case("artifact-diff: an unresolvable head-ref prints nothing on stdout",
         bad_head.stdout, "")

    with tempfile.TemporaryDirectory() as tmp:
        not_a_repo = Path(tmp) / "not-a-repo"
        not_a_repo.mkdir()
        (not_a_repo / "images").mkdir()
        got = run_diff(not_a_repo, "a", "b")
    case("artifact-diff: --repo pointing at a non-git directory exits 2",
         got.returncode, 2)
    case("artifact-diff: a non-git --repo prints nothing on stdout",
         got.stdout, "")


def worktree_leak_cases():
    with tempfile.TemporaryDirectory() as tmp:
        fixture = init_repo(Path(tmp) / "fixture")
        write_triple(image_dir(fixture), pkgver="curl 8.7.1-r0\n")
        base = commit(fixture, "base")
        write_triple(image_dir(fixture), pkgver="curl 8.9.0-r0\n")
        head = commit(fixture, "bump curl")
        expected = real_diff(fixture, base, head)

        hostile = init_repo(Path(tmp) / "hostile")
        commit(hostile, "unrelated hostile commit")

        hostile_env = clean_env(GIT_DIR=str(hostile / ".git"),
                                GIT_WORK_TREE=str(hostile))
        got = subprocess.run(
            [sys.executable, str(ARTIFACT_DIFF), "--repo", str(fixture),
             base, head],
            capture_output=True, text=True, env=hostile_env)
    case("artifact-diff: a leaked GIT_DIR/GIT_WORK_TREE does not divert "
         "--repo away from the fixture (still exits 0)", got.returncode, 0)
    case("artifact-diff: a leaked GIT_DIR/GIT_WORK_TREE still yields the "
         "fixture's own diff on stdout", got.stdout, expected)


def main() -> int:
    empty_delta_cases()
    changed_cases()
    could_not_tell_cases()
    worktree_leak_cases()
    print(f"\npass={len(PASS)} fail={len(FAIL)} skip=0")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
