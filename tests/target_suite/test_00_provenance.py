"""SRS008/TST008: the booted board's own `/etc/buildinfo` names the layer commit under test, the
same field `tools/reproducibility-gate.sh` parses to refuse an image whose own build does not
match its claim.
"""

import os
import re

_BUILDINFO_LINE = re.compile(r"^meta-wisekiosk\s+=\s+(\S+)", re.MULTILINE)


def _layer_commit(buildinfo):
    """The sha from `/etc/buildinfo`'s "meta-wisekiosk = <branch>:<sha>[ -- modified]" line
    (image-buildinfo writes "%-17s = %s:%s%s" per BBLAYERS entry), or "" if no such line."""
    match = _BUILDINFO_LINE.search(buildinfo.replace("\r", ""))
    if not match:
        return ""
    return match.group(1).rpartition(":")[-1]


def test_buildinfo_names_the_commit_under_test(target, record_property):
    driver = target.get_driver("SSHDriver")
    stdout, stderr, returncode = driver.run("cat /etc/buildinfo")
    assert returncode == 0, f"could not read /etc/buildinfo: {stderr}"
    buildinfo = "\n".join(stdout)
    record_property("buildinfo", buildinfo)
    assert _layer_commit(buildinfo) == os.environ["BENCH_SHA"]
