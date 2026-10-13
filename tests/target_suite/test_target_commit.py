"""Target suite: the booted image update names the commit it was built from."""

import pytest


def test_buildinfo_names_commit(target, bench_candidate, record_property):
    """TST016: after an image update, /etc/buildinfo names the installed commit.

    Skipped when `bench_candidate` is None -- no candidate was built this run (a plain
    pytest invocation outside the runner). image-buildinfo writes one line per BBLAYERS
    entry as "<layer> = <branch>:<sha>[ -- modified]"; parsed the same way as
    tools/reproducibility-gate.sh's own buildinfo check.
    """
    if bench_candidate is None:
        pytest.skip("no bench_candidate: not running under bench test/bench run")
    record_property("requirement", "TST016")
    expected = bench_candidate
    driver = target.get_driver("SSHDriver")
    stdout, _stderr, returncode = driver.run("cat /etc/buildinfo")
    assert returncode == 0, "could not read /etc/buildinfo on the board"
    line = next(
        (entry for entry in stdout if entry.split()[:2] == ["meta-wisekiosk", "="]),
        None,
    )
    assert line is not None, f"no meta-wisekiosk layer line in buildinfo:\n{chr(10).join(stdout)}"
    commit = line.split()[2].rsplit(":", 1)[-1]
    assert commit == expected, f"board reports commit {commit}, expected {expected} (bench_candidate)"
