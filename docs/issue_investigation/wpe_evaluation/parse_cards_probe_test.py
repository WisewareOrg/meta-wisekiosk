#!/usr/bin/env python3
"""Tests for parse_cards_probe, the #185 cards-live probe parser. code-monkey keeps this suite
green without modifying it.

Payload format:

    CP|t=<sec>|c=<n>|l=<n>

  t  seconds since page load (int)
  c  [data-pwt-card] elements present right now
  l  of those, how many also hold [data-pwt-leaderboard] (live data rendered, not closed or
     API-failed)

The gate for "all 4 cards live" is c=4 AND l=4 on EVERY sample in the window being judged --
one short sample anywhere in a smoothness/soak capture must VOID the whole thing, never average
away. all_live() must also raise on zero samples (a dead probe is not "vacuously live").

Run: python3 parse_cards_probe_test.py
"""
import parse_cards_probe as pcp

fails = 0


def check(name, cond, detail=""):
    global fails
    status = "PASS" if cond else "FAIL"
    if not cond:
        fails += 1
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))


SAMPLE = "CP|t=120|c=4|l=4"
MALFORMED = "CP|t=120|c=4"
NOT_A_PAYLOAD = "the quick brown fox"

ALL_LIVE = [
    "CP|t=0|c=4|l=4",
    "CP|t=30|c=4|l=4",
    "CP|t=60|c=4|l=4",
]

# The exact seeded defect this gate exists to catch: one sample mid-run drops to l=3 (a park's
# leaderboard stopped rendering partway through), everything else is c=4 l=4. A gate that only
# checks the first or last sample, or averages, would pass this. It must VOID.
ONE_SHORT_SAMPLE = [
    "CP|t=0|c=4|l=4",
    "CP|t=30|c=4|l=3",   # the seed: one park's leaderboard not live this sample
    "CP|t=60|c=4|l=4",
]

CLOSED_PARK = [
    "CP|t=0|c=4|l=3",
    "CP|t=30|c=4|l=3",
]


def test_parse_sample():
    d = pcp.parse(SAMPLE)
    check("parse(SAMPLE) returns a dict", d is not None)
    check("parse(SAMPLE).t", d["t"] == 120)
    check("parse(SAMPLE).c", d["c"] == 4)
    check("parse(SAMPLE).l", d["l"] == 4)


def test_parse_rejects_malformed():
    check("parse(MALFORMED) is None", pcp.parse(MALFORMED) is None)
    check("parse(NOT_A_PAYLOAD) is None", pcp.parse(NOT_A_PAYLOAD) is None)


def test_all_live_true_when_every_sample_is_4_4():
    check("all_live(ALL_LIVE) is True", pcp.all_live(ALL_LIVE) is True)


def test_all_live_false_on_one_short_sample():
    # This is the proof the gate can fail: a single l=3 sample anywhere in an otherwise-live
    # run must flip the whole run to VOID.
    check("all_live(ONE_SHORT_SAMPLE) is False", pcp.all_live(ONE_SHORT_SAMPLE) is False)


def test_all_live_false_when_closed():
    check("all_live(CLOSED_PARK) is False", pcp.all_live(CLOSED_PARK) is False)


def test_all_live_raises_when_nothing_parses():
    # A dead probe (never ran, or every line is noise) must never read as "vacuously live".
    for name, lines in (("zero parseable lines", ["# only noise", MALFORMED, NOT_A_PAYLOAD]),
                         ("an empty list", [])):
        try:
            pcp.all_live(lines)
        except ValueError:
            check(f"all_live({name}) raises ValueError", True)
        else:
            check(f"all_live({name}) raises ValueError", False)


def test_live_fraction():
    check("live_fraction(ALL_LIVE) == 1.0", pcp.live_fraction(ALL_LIVE) == 1.0)
    check("live_fraction(ONE_SHORT_SAMPLE) == 2/3",
          abs(pcp.live_fraction(ONE_SHORT_SAMPLE) - 2 / 3) < 1e-9)
    check("live_fraction(CLOSED_PARK) == 0.0", pcp.live_fraction(CLOSED_PARK) == 0.0)


def test_main_prints_void_on_one_short_sample(tmp_path_str=None):
    import io, contextlib, tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write("\n".join(ONE_SHORT_SAMPLE) + "\n")
        path = f.name
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pcp.main(path)
        out = buf.getvalue()
        check("main() prints VOID for a one-short-sample capture", "VOID" in out, detail=out)
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_parse_sample()
    test_parse_rejects_malformed()
    test_all_live_true_when_every_sample_is_4_4()
    test_all_live_false_on_one_short_sample()
    test_all_live_false_when_closed()
    test_all_live_raises_when_nothing_parses()
    test_live_fraction()
    test_main_prints_void_on_one_short_sample()
    print()
    if fails:
        raise SystemExit(f"{fails} check(s) FAILED")
    print("all checks passed")
