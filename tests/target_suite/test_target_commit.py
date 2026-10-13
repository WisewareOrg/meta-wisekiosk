"""Target suite: the booted image update names the commit it was built from."""

import pytest


def test_buildinfo_names_commit(target, bench_candidate, record_property):
    """TST016: after an image update, /etc/buildinfo names the installed commit.

    Records the board's commit as `board_commit` on every run, before the skip decision.
    Skipped when `bench_candidate` is None -- a plain pytest invocation outside the
    runner, or `bench test <ref> --skip-build`, which runs this suite against the board
    as it is with no candidate built. image-buildinfo writes one line per BBLAYERS entry
    as "<layer> = <branch>:<sha>[ -- modified]".
    """
    driver = target.get_driver("SSHDriver")
    stdout, _stderr, returncode = driver.run("cat /etc/buildinfo")
    assert returncode == 0, "could not read /etc/buildinfo on the board"
    line = next(
        (entry for entry in stdout if entry.split()[:2] == ["meta-wisekiosk", "="]),
        None,
    )
    assert line is not None, f"no meta-wisekiosk layer line in buildinfo:\n{chr(10).join(stdout)}"
    board_commit = line.split()[2].rsplit(":", 1)[-1]
    record_property("board_commit", board_commit)
    if bench_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    record_property("requirement", "TST016")
    assert board_commit == bench_candidate, (
        f"board reports commit {board_commit}, expected {bench_candidate} (bench_candidate)"
    )
