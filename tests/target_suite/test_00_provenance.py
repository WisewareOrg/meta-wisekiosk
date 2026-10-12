"""The booted board's own `/etc/buildinfo` names the layer commit under test, the same field
`tools/reproducibility-gate.sh` parses to refuse an image whose own build does not match its
claim. Parsing is `framework.record.parse_buildinfo`, covered by its own unit test
(`meta-wisekiosk/lib/oeqa/runtime/framework/tests/test_record.py`) rather than here.
"""

import os

from framework.record import parse_buildinfo


def test_buildinfo_names_the_commit_under_test(target, record_property):
    """Assert the booted board's `/etc/buildinfo` names `BENCH_SHA`, and record the raw line.

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.
        record_property: pytest's own fixture; attaches the raw `/etc/buildinfo` text to this
            test's report entry under the key `"buildinfo"`.
    """
    driver = target.get_driver("SSHDriver")
    stdout, stderr, returncode = driver.run("cat /etc/buildinfo")
    assert returncode == 0, f"could not read /etc/buildinfo: {stderr}"
    buildinfo = "\n".join(stdout)
    record_property("buildinfo", buildinfo)
    assert parse_buildinfo(buildinfo) == os.environ["BENCH_SHA"]
