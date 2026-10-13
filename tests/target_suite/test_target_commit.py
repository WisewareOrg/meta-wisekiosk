"""Target suite: the booted image update names the commit it was built from."""

import os


def test_buildinfo_names_commit(target, record_property):
    """TST016: after an image update, /etc/buildinfo names the installed commit.

    image-buildinfo writes one line per BBLAYERS entry as
    "<layer> = <branch>:<sha>[ -- modified]"; parsed the same way as
    tools/reproducibility-gate.sh's own buildinfo check.
    """
    record_property("requirement", "TST016")
    expected = os.environ["BENCH_SHA"]
    driver = target.get_driver("SSHDriver")
    stdout, _stderr, returncode = driver.run("cat /etc/buildinfo")
    assert returncode == 0, "could not read /etc/buildinfo on the board"
    line = next(
        (entry for entry in stdout if entry.split()[:2] == ["meta-wisekiosk", "="]),
        None,
    )
    assert line is not None, f"no meta-wisekiosk layer line in buildinfo:\n{chr(10).join(stdout)}"
    commit = line.split()[2].rsplit(":", 1)[-1]
    assert commit == expected, f"board reports commit {commit}, expected {expected} (BENCH_SHA)"
