#!/usr/bin/env python3
"""Tests for journal_extract.last_parseable, the #185 W2 journal/console line reader.

journal_extract does not exist yet -- this file is its spec, code-monkey makes it green.

#185's harness needs to read a smoothness (MP|) or module-fault (MF|) payload back from a
journal capture on WPE, where there is no xprop/xwininfo to read a title property directly
(removed in W1): instead, a run's evidence is `journalctl -u kiosk`'s own text, which holds
TWO kinds of line carrying the payload --
  - "TITLE <title>\\n" on every title change (the carried cog patch,
    0001-launcher-add-user-script-option.patch: `g_print("TITLE %s\\n", ...)`), which is how
    a probe writing to document.title (p7_min.js, mf-probe.js, both unchanged) reaches the
    journal with no X at all;
  - a plain console line (cog's upstream --enable-write-console-messages-to-stdout, if a
    probe or future instrumentation uses console.log instead), format not otherwise pinned.
Both are journalctl lines first, so EVERY line also carries journalctl's own
"<mon> <day> <time> <host> <unit>[<pid>]: " prefix ahead of whichever of the two above.

last_parseable does NOT need to know any of these prefixes, carried patch or not: it reuses
parse_smoothness.parse / parse_module_fault.parse UNCHANGED, which already find their own
"MP|"/"MF|" marker with re.search (not anchored), so any prefix text -- journalctl's, "TITLE
", a hypothetical console format, or none -- is already tolerated. What's new here is purely
the "which line, out of a whole noisy capture" step every existing parse_*.py's own __main__
already does ad hoc (lines = [l for l in text if 'MP|' in l]; parse(lines[-1])) -- generalised
once, proven both ways, and reused for MP| and MF| alike instead of copied per probe.

Contract:

    last_parseable(lines, parse_fn) -> parse_fn's return value for the LAST line in `lines`
    that parse_fn can parse, or None if no line parses.

  lines: an iterable of individual line strings (a journal capture already split on "\\n").
  parse_fn: parse_smoothness.parse or parse_module_fault.parse (any single-line parser with
    that signature -- this suite exercises it with both, proving it is not hardcoded to one
    probe's marker).

Run: python3 journal_extract_test.py
"""
import journal_extract as je
import parse_smoothness as ps
import parse_module_fault as pmf

fails = 0


def check(name, cond, detail=""):
    global fails
    status = "PASS" if cond else "FAIL"
    if not cond:
        fails += 1
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))


MP_EARLY = "MP|100|f6000|av50|mx500|BT2|H5000.600.300.80.15.4.1|B1.0:300,5:260"
MP_LATE = "MP|500|f8000|av60|mx1200|BT3|H7000.500.300.150.30.15.5|B1.9:300,2.2:1079,400:260"
MF_EARLY = "MF|t=30|f=0|fmax=0|fever=0|u=0|umax=0"
MF_LATE = "MF|t=120|f=1|fmax=2|fever=3|u=0|umax=1"

JOURNAL_PREFIX = "Oct 04 15:40:01 kiosk kiosk-launch[123]: "


def test_extracts_a_title_prefixed_line():
    lines = [JOURNAL_PREFIX + "systemd starting", JOURNAL_PREFIX + "TITLE " + MP_LATE]
    d = je.last_parseable(lines, ps.parse)
    check("last_parseable finds the TITLE-prefixed MP| line", d is not None and d["sec"] == 500,
          detail=str(d))


def test_extracts_an_unprefixed_console_style_line():
    # No "TITLE " tag at all -- just journalctl's own prefix ahead of the payload, standing
    # in for whatever a plain console.log line looks like. Proves the extraction does not
    # key on "TITLE " specifically.
    lines = [JOURNAL_PREFIX + "CONSOLE 1 > " + MP_LATE]
    d = je.last_parseable(lines, ps.parse)
    check("last_parseable finds an unprefixed (non-TITLE) MP| line",
          d is not None and d["sec"] == 500, detail=str(d))


def test_prefers_the_last_matching_line_not_the_first():
    lines = [
        JOURNAL_PREFIX + "TITLE " + MP_EARLY,
        JOURNAL_PREFIX + "some unrelated journal line",
        JOURNAL_PREFIX + "TITLE " + MP_LATE,
    ]
    d = je.last_parseable(lines, ps.parse)
    check("last_parseable returns the LAST payload (sec=500), not the first (sec=100)",
          d is not None and d["sec"] == 500, detail=str(d))


def test_returns_none_when_nothing_parses():
    lines = [JOURNAL_PREFIX + "systemd starting", JOURNAL_PREFIX + "Started kiosk.service"]
    d = je.last_parseable(lines, ps.parse)
    check("last_parseable returns None on a dead/noise-only journal", d is None, detail=str(d))


def test_works_identically_for_the_module_fault_parser():
    # Not hardcoded to MP| -- the same function, unchanged, serves MF| by passing a
    # different parse_fn.
    lines = [
        JOURNAL_PREFIX + "TITLE " + MF_EARLY,
        JOURNAL_PREFIX + "TITLE " + MF_LATE,
    ]
    d = je.last_parseable(lines, pmf.parse)
    check("last_parseable(..., parse_module_fault.parse) returns the last MF| sample "
          "(fever=3), not the first (fever=0)",
          d is not None and d["fever"] == 3, detail=str(d))


if __name__ == "__main__":
    test_extracts_a_title_prefixed_line()
    test_extracts_an_unprefixed_console_style_line()
    test_prefers_the_last_matching_line_not_the_first()
    test_returns_none_when_nothing_parses()
    test_works_identically_for_the_module_fault_parser()
    print()
    if fails:
        raise SystemExit(f"{fails} check(s) FAILED")
    print("all checks passed")
