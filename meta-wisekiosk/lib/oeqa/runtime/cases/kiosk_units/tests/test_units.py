"""Specifies cases/kiosk_units/verdict.py (#206, step 4 of #202; brief.md "Correction", owner,
2026-10-08): `systemd-analyze verify`'s own classification, moved here from `kiosk_image/verdict.py`
-- a device-tier check (`case.py` runs `systemd-analyze verify <unit>` on the board over
`self.target.run`, no `--root`), not a host-side read of the build's own rootfs.

The classification's contract is unchanged by the move -- `systemd_analyze_verdict(returncode,
stderr_text)` returns ("ok"/"warning"/"error", reason), identical in shape to
`kiosk_render.verdict`/`kiosk_layout.verdict` and to the function this replaces -- only the
grounding changes: `--root` mode's own false positives (the unrelated-unit stderr cross-talk and
the `data.mount`-not-found failure that `kiosk_image/case.py`'s filter exists to strip) do not
apply on a live, running board, so this file grounds every branch on a plain `systemd-analyze
verify <unit>` call against this host's own real units -- no `--root`, no filter.

One parametrized test, one row per code branch (the round-3 dispatch's "one test per branch"):
rc=0 with stripped-empty stderr is "ok"; rc=0 with a non-empty stripped stderr is "warning" (NOT
distinguishable from "ok" by returncode alone); nonzero rc with non-blank stderr lines is "error"
naming every one of them; nonzero rc with nothing in stderr is "error" naming the bare returncode.

Grounded this session against real `systemd-analyze verify` output on this host (systemd 259,
`systemd-analyze --version`), no `--root`:
- `systemd-analyze verify systemd-networkd.service` (a real, already-loaded system unit): rc=0,
  stderr empty -- the real "ok" shape.
- A unit carrying an unrecognised directive, verified with `systemd-analyze --user verify`: rc=0,
  stderr `"<path>:<line>: Unknown key '<Key>' in section [<Section>], ignoring."` -- the real
  "warning" shape (rc=0, non-empty stderr), confirming "warning" is genuinely not distinguishable
  from "ok" by returncode alone. `WARNING_LINE` below carries that exact real format; the unit
  path/name is substituted for one in this project rather than this session's own workstation
  path, which the format does not depend on.
- A unit `Requires=`/`After=` a mount unit that does not exist, verified the same way: rc=1,
  stderr `"<unit>: Failed to create <unit>/start: Unit <dep> not found."` -- the real "error"
  shape for a load failure. `ERROR_LINE` below is that real line verbatim (unit names
  `fail-grounding.service`/`does-not-exist.mount`, not identifying).
"""

import pytest

from oeqa.runtime.cases.kiosk_units.verdict import systemd_analyze_verdict

# Real format confirmed by `systemd-analyze --user verify` against an unrecognised-directive
# unit on this host (systemd 259) -- see module docstring. The file path is this project's own
# display unit, substituted for this session's workstation path, which the real format does not
# depend on.
WARNING_LINE = (
    "/usr/lib/systemd/system/kiosk.service:7: Unknown key 'NotARealDirective' "
    "in section [Service], ignoring."
)

# The real stderr line from `systemd-analyze --user verify` against a unit requiring a mount
# that does not exist on this host (systemd 259) -- see module docstring.
ERROR_LINE = "fail-grounding.service: Failed to create fail-grounding.service/start: Unit does-not-exist.mount not found."
SECOND_ERROR_LINE = "fail-grounding.service: Failed to enqueue stop job."


@pytest.mark.parametrize(
    ("name", "returncode", "stderr_text", "want_outcome", "want_reason_contains"),
    [
        ("clean verify, no output at all", 0, "", "ok", ()),
        ("clean exit, stderr present but only blank lines", 0, "\n  \n", "ok", ()),
        ("clean exit but a real non-fatal finding, named", 0, WARNING_LINE, "warning", ("Unknown key", "ignoring")),
        ("real load failure, dependency named", 1, ERROR_LINE, "error", ("does-not-exist.mount",)),
        (
            "nonzero exit, multiple stderr lines, all named",
            1,
            ERROR_LINE + "\n" + SECOND_ERROR_LINE,
            "error",
            ("does-not-exist.mount", "enqueue stop job"),
        ),
        ("nonzero exit with no stderr captured at all, returncode named", 139, "", "error", ("139",)),
    ],
)
def test_systemd_analyze_verdict_outcome(name, returncode, stderr_text, want_outcome, want_reason_contains):
    outcome, reason = systemd_analyze_verdict(returncode, stderr_text)
    assert outcome == want_outcome, f"{name}: {reason!r}"
    for token in want_reason_contains:
        assert token in reason, f"{name}: {token!r} not in {reason!r}"
