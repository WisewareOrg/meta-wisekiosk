"""Specifies cases/kiosk_render/verdict.py: a port of tools/kiosk-render-check.sh's render_verdict
over the same probe vocabulary -- "cap import=0", "frame <n> rc=<rc> bytes=<b> md5=<m>", "blank
min=<mn> max=<mx>" -- as a list of lines rather than one shell string. Every case here ports a case
in tools/kiosk-render-check-test.sh.

No device, no subprocess -- every case is a constructed list of probe lines.
"""

import pytest

from oeqa.runtime.cases.kiosk_render.verdict import verdict

A = "5d41402abc4b2a76b9719d911017c592"
B = "7d793037a0760186574b0282f2f435e7"
EMPTY_MD5 = "d41d8cd98f00b204e9800998ecf8427e"
MIN_BYTES = 100
CAP = ["cap import=1", "cap identify=1", "crop 560x300+220+20"]
NOTBLANK = "blank min=0 max=255 mean=4.2"


def frame(n, *, rc=0, bytes_=1840, md5=A):
    return f"frame {n} rc={rc} at=10:43:1{n} bytes={bytes_} md5={md5}"


CASES = [
    ("identical hashes are FROZEN",
     CAP + [frame(1), frame(2), NOTBLANK], "frozen"),
    ("identical hashes, differing byte counts, still FROZEN -- the hash is the key, not the size",
     CAP + [frame(1, bytes_=1840), frame(2, bytes_=1841), NOTBLANK], "frozen"),
    ("FROZEN with no blank line at all -- identify absent must not block the verdict",
     ["cap import=1", "cap identify=0", frame(1), frame(2)], "frozen"),
    ("differing hashes are advancing",
     CAP + [frame(1, md5=A), frame(2, md5=B), NOTBLANK], "advancing"),
    ("advancing with no blank line at all",
     ["cap import=1", "cap identify=0", frame(1, md5=A), frame(2, md5=B)], "advancing"),
    ("an import warning on stderr is not itself a failure -- rc is the authority",
     CAP + [frame(1, md5=A), "err import: geometry does not contain image", frame(2, md5=B), NOTBLANK],
     "advancing"),
    ("a failed first capture is error, never FROZEN, though both hashes agree",
     CAP + [frame(1, rc=1, bytes_=0, md5="none"), frame(2)], "error"),
    ("both captures failed is error, never FROZEN",
     CAP + [frame(1, rc=1, bytes_=0, md5="none"), frame(2, rc=1, bytes_=0, md5="none")], "error"),
    ("non-zero rc with an otherwise plausible, identical frame is error -- the rc guard's own pin",
     CAP + [frame(1, rc=1), frame(2, rc=1), NOTBLANK], "error"),
    ("one non-zero rc among differing hashes is error, not advancing",
     CAP + [frame(1, rc=0, md5=A), frame(2, rc=2, md5=B), NOTBLANK], "error"),
    ("md5 of empty input is error, never FROZEN, even at a plausible byte count",
     CAP + [frame(1, md5=EMPTY_MD5), frame(2, md5=EMPTY_MD5), NOTBLANK], "error"),
    ("a short frame (bytes=0) is error, never FROZEN",
     CAP + [frame(1, bytes_=0), frame(2, bytes_=0)] + [NOTBLANK], "error"),
    ("one byte under MIN_BYTES is error",
     CAP + [frame(1, bytes_=MIN_BYTES - 1), frame(2, bytes_=1840, md5=B), NOTBLANK], "error"),
    ("exactly MIN_BYTES is accepted -- the boundary is numeric, not bytes=0",
     CAP + [frame(1, bytes_=MIN_BYTES), frame(2, bytes_=1840, md5=B), NOTBLANK], "advancing"),
    ("no import on the device is error", ["cap import=0"], "error"),
    ("an empty probe is error", [], "error"),
    ("one frame only is error -- nothing to compare",
     CAP + [frame(1), NOTBLANK], "error"),
    ("three frames is error -- as broken a comparison as one",
     CAP + [frame(1), frame(2), "frame 3 rc=0 at=10:43:18 bytes=1840 md5=" + A, NOTBLANK], "error"),
    ("a uniform (all-black) captured region is error, not FROZEN",
     CAP + [frame(1, bytes_=180), frame(2, bytes_=180), "blank min=0 max=0 mean=0"], "error"),
    ("a uniform all-white region is error too -- not just zero",
     CAP + [frame(1, bytes_=180), frame(2, bytes_=180), "blank min=255 max=255 mean=255"], "error"),
    ("min differing from max by one is a real verdict, not uniform",
     CAP + [frame(1), frame(2), "blank min=0 max=1 mean=0.02"], "frozen"),
    ("a frame line missing its md5 field entirely is error -- never compared as equal strings",
     CAP + ["frame 1 rc=0 at=10:43:10 bytes=1840", "frame 2 rc=0 at=10:43:14 bytes=1840", NOTBLANK],
     "error"),
]


@pytest.mark.parametrize(("name", "lines", "want_outcome"), CASES, ids=[c[0] for c in CASES])
def test_verdict_outcome(name, lines, want_outcome):
    outcome, reason = verdict(lines)
    assert outcome == want_outcome, f"{name}: got {outcome!r} ({reason!r})"
    assert reason, f"{name}: reason must not be empty"


# Each could-not-tell case above is distinguishable from every other by its reason: a verdict that
# collapsed every guard into one generic "error" message would still pass test_verdict_outcome above.
REASON_SUBSTRINGS = [
    ("no import on the device is error", "import"),
    ("one frame only is error -- nothing to compare", "frame"),
    ("three frames is error -- as broken a comparison as one", "frame"),
    ("non-zero rc with an otherwise plausible, identical frame is error -- the rc guard's own pin",
     "rc"),
    ("one byte under MIN_BYTES is error", "byte"),
    ("md5 of empty input is error, never FROZEN, even at a plausible byte count", "empty"),
    ("a uniform (all-black) captured region is error, not FROZEN", "uniform"),
    ("a frame line missing its md5 field entirely is error -- never compared as equal strings",
     "md5"),
]


@pytest.mark.parametrize(("name", "substring"), REASON_SUBSTRINGS, ids=[c[0] for c in REASON_SUBSTRINGS])
def test_verdict_reason_names_its_own_guard(name, substring):
    by_name = {c[0]: c[1] for c in CASES}
    _, reason = verdict(by_name[name])
    assert substring in reason.lower(), f"{name}: reason {reason!r} does not mention {substring!r}"


def test_verdict_rc_error_reason_folds_in_the_frame_s_stderr():
    # The probe always carries import's own stderr as a trailing err= field on
    # the frame line (kiosk.py's grab(): "frame $n rc=$rc bytes=$b md5=$m
    # err=${err:-none}", spaces turned to underscores). When rc != 0, the
    # reason must surface it, not just point at the rc field.
    lines = [
        'frame 1 rc=1 bytes=0 md5=none err=import:_unable_to_open_X_server_`:0`',
        f"frame 2 rc=0 bytes=1840 md5={A}",
    ]
    outcome, reason = verdict(lines)
    assert outcome == "error"
    assert "import:_unable_to_open_X_server_`:0`" in reason
