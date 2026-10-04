#!/usr/bin/env python3
"""RED tests for parse_smoothness, the #185 smoothness-probe parser.

parse_smoothness does not exist yet -- this file is the spec code-monkey makes green,
proven both ways on synthetic payloads (measure-first; parse_motion_test.py precedent).

Payload spec (unmodified gpu_compositing/p7_min.js, confirmed against its source,
2026-10-04):

    MP|<sec>|f<frames>|av<avgMs>|mx<maxMs>|BT<bigTotal>|H<h0>.<h1>.<h2>.<h3>.<h4>.<h5>.<h6>|B<big>

  hist buckets (edges 50,100,250,500,1000,2000 ms): h0 = <50ms, h1..h6 the rest, in order.
  big = comma-separated "<t_s>:<dt_ms>" pairs, chronological (oldest first), the LAST 14
  frames >250ms seen so far (p7_min.js:37-38 pushes to the end and shifts the front past
  14 -- the OLDEST entries are evicted first, not the newest).

Judged stats (#185 plan "Smoothness statistics"; owner rulings 2026-10-04):
  - pct_under_50ms, mean_fps: FULL capture, not windowed.
  - steady_stall_rate: count of big[] entries with t >= 15.0 s, divided by (sec - 15.0).
    Exact ONLY when bt == len(big) -- nothing yet evicted.
  - steady_stall_bounds: the bt > len(big) case (orchestrator ruling 2026-10-04). Returns
    {"bounded": bool, "lower": int, "upper": int, "lower_rate": float, "upper_rate": float}.
      bounded=False (bt == len(big)): lower == upper == the exact steady count; both rates
        equal steady_stall_rate's value.
      bounded=True (bt > len(big)): big[] has evicted its oldest entries, so the exact
        steady count can't be recovered --
          lower = count of RETAINED big[] entries with t >= 15.0 s (a floor: more
                  qualifying events may have been evicted, since the oldest go first).
          upper = bt - (count of RETAINED big[] entries with t < 15.0 s) (a ceiling: the
                  most favourable case, assuming every evicted entry was pre-steady-state).
        Both rates divide by (sec - 15.0). The verdict's 3-way rule on these bounds
        (regression / pass / "judged on upper bound") is tested in verdict_test.py, not
        here -- this file only proves the parser's bound computation.
  - clusters: recorded, not judged. Consecutive big[] entries (sorted by t, as emitted)
    merge into one cluster when the gap between them is <= 1.0 s (the ruling's "1000 ms").

Run: python3 parse_smoothness_test.py
"""
import parse_smoothness as ps

fails = 0


def check(name, cond, detail=""):
    global fails
    status = "PASS" if cond else "FAIL"
    if not cond:
        fails += 1
    print(f"[{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))


# --- CLEAN: three >250ms frames, two startup (t<15) that merge into one cluster
# (gap 0.3s <= 1.0s), one steady-state (t=400) that stands alone. bt == len(big) == 3.
CLEAN = "MP|500|f8000|av60|mx1200|BT3|H7000.500.300.150.30.15.5|B1.9:300,2.2:1079,400:260"

# --- NO_STEADY_STALLS: both >250ms frames are before t=15; steady window has none.
# Proves the rate reports an exact 0.0, not None/error, when the window is clean.
NO_STEADY_STALLS = "MP|100|f6000|av50|mx500|BT2|H5000.600.300.80.15.4.1|B1.0:300,5:260"

# --- BOUNDED: bt=20 > len(big)=14 -- big[] has evicted its 6 oldest entries. Of the 14
# retained, 2 are pre-steady (t=1, t=3) and 12 are >=15s. lower=12, upper=20-2=18.
BOUNDED = ("MP|600|f30000|av20|mx1500|BT20|H29000.600.300.70.20.8.2"
           "|B1:300,3:300,20:300,25:300,30:300,100:300,150:300,200:300,250:300,300:300,"
           "350:300,400:300,450:300,500:300")

# --- MALFORMED: truncated payload, must not parse.
MALFORMED = "MP|500|f8000"

# --- NOT_A_PAYLOAD: unrelated text, must not parse.
NOT_A_PAYLOAD = "the quick brown fox"


def test_parse_clean():
    d = ps.parse(CLEAN)
    check("parse(CLEAN) returns a dict", d is not None)
    check("parse(CLEAN).sec", d["sec"] == 500)
    check("parse(CLEAN).frames", d["frames"] == 8000)
    check("parse(CLEAN).avg", d["avg"] == 60)
    check("parse(CLEAN).max", d["max"] == 1200)
    check("parse(CLEAN).bt", d["bt"] == 3)
    check("parse(CLEAN).hist", d["hist"] == [7000, 500, 300, 150, 30, 15, 5])
    check("parse(CLEAN).big", d["big"] == [(1.9, 300), (2.2, 1079), (400.0, 260)],
          detail=str(d["big"]))


def test_parse_rejects_malformed():
    check("parse(MALFORMED) is None", ps.parse(MALFORMED) is None)
    check("parse(NOT_A_PAYLOAD) is None", ps.parse(NOT_A_PAYLOAD) is None)


def test_pct_under_50ms_full_capture():
    d = ps.parse(CLEAN)
    # 7000 of 8000 frames in bucket 0 (<50ms), over the FULL capture, not windowed.
    check("pct_under_50ms(CLEAN) == 87.5", ps.pct_under_50ms(d) == 87.5)
    d2 = ps.parse(NO_STEADY_STALLS)
    check("pct_under_50ms(NO_STEADY_STALLS) == 83.333...",
          abs(ps.pct_under_50ms(d2) - (100.0 * 5000 / 6000)) < 1e-9)


def test_mean_fps_full_capture():
    d = ps.parse(CLEAN)
    # frames / sec, matching Runs 49-53's own tables and parse_min.py -- NOT 1000/avg.
    check("mean_fps(CLEAN) == 16.0", ps.mean_fps(d) == 8000 / 500)
    d2 = ps.parse(NO_STEADY_STALLS)
    check("mean_fps(NO_STEADY_STALLS) == 60.0", ps.mean_fps(d2) == 6000 / 100)


def test_steady_stall_rate_counts_only_t_ge_15():
    d = ps.parse(CLEAN)
    assert d["bt"] == len(d["big"]), "fixture must satisfy bt == len(big)"
    # Only the t=400 entry is >= 15s; the two startup entries (1.9, 2.2) are excluded.
    # count=1, denom = sec - 15 = 485.
    want = 1 / (500 - 15)
    check("steady_stall_rate(CLEAN) excludes startup frames",
          abs(ps.steady_stall_rate(d) - want) < 1e-9,
          detail=f"got {ps.steady_stall_rate(d)!r} want {want!r}")


def test_steady_stall_rate_reports_exact_zero_when_none_qualify():
    d = ps.parse(NO_STEADY_STALLS)
    assert d["bt"] == len(d["big"]), "fixture must satisfy bt == len(big)"
    check("steady_stall_rate(NO_STEADY_STALLS) == 0.0",
          ps.steady_stall_rate(d) == 0.0)


def test_clusters_merges_within_1s_and_splits_beyond_it():
    d = ps.parse(CLEAN)
    cl = ps.clusters(d)
    # (1.9,300) and (2.2,1079) are 0.3s apart -> one cluster of 2.
    # (400.0,260) is far from both -> its own cluster of 1.
    check("clusters(CLEAN) has 2 clusters", len(cl) == 2, detail=str(cl))
    check("clusters(CLEAN) first cluster has 2 members",
          len(cl) == 2 and len(cl[0]) == 2, detail=str(cl))
    check("clusters(CLEAN) second cluster has 1 member",
          len(cl) == 2 and len(cl[1]) == 1, detail=str(cl))


def test_clusters_does_not_merge_everything():
    # NOT_A_PAYLOAD / MALFORMED can't reach clusters() (parse returns None for both);
    # use NO_STEADY_STALLS instead: its two big entries (1.0, 5.0) are 4.0s apart,
    # well past the 1.0s gap -- a clustering bug that merges everything would collapse
    # this to one cluster and this check would catch it.
    d = ps.parse(NO_STEADY_STALLS)
    cl = ps.clusters(d)
    check("clusters(NO_STEADY_STALLS) does not merge a 4.0s gap",
          len(cl) == 2, detail=str(cl))


def test_steady_stall_bounds_exact_matches_steady_stall_rate_when_nothing_evicted():
    d = ps.parse(CLEAN)
    assert d["bt"] == len(d["big"]), "fixture must satisfy bt == len(big)"
    b = ps.steady_stall_bounds(d)
    want_rate = ps.steady_stall_rate(d)
    check("steady_stall_bounds(CLEAN).bounded is False", b["bounded"] is False, detail=str(b))
    check("steady_stall_bounds(CLEAN).lower == upper == 1",
          b["lower"] == 1 and b["upper"] == 1, detail=str(b))
    check("steady_stall_bounds(CLEAN) rates equal steady_stall_rate's exact value",
          b["lower_rate"] == b["upper_rate"] == want_rate, detail=str(b))


def test_steady_stall_bounds_reports_bounded_when_big_is_truncated():
    d = ps.parse(BOUNDED)
    check("parse(BOUNDED).bt == 20", d["bt"] == 20)
    check("parse(BOUNDED) big[] truncated to 14", len(d["big"]) == 14)
    b = ps.steady_stall_bounds(d)
    check("steady_stall_bounds(BOUNDED).bounded is True", b["bounded"] is True, detail=str(b))
    check("steady_stall_bounds(BOUNDED).lower == 12 (retained entries with t>=15)",
          b["lower"] == 12, detail=str(b))
    check("steady_stall_bounds(BOUNDED).upper == 18 (bt=20 minus the 2 retained pre-15 entries)",
          b["upper"] == 18, detail=str(b))
    check("steady_stall_bounds(BOUNDED).lower_rate == 12/585",
          abs(b["lower_rate"] - 12 / 585) < 1e-9, detail=str(b))
    check("steady_stall_bounds(BOUNDED).upper_rate == 18/585",
          abs(b["upper_rate"] - 18 / 585) < 1e-9, detail=str(b))
    check("steady_stall_bounds(BOUNDED) lower < upper (a real bound, not a collapsed point)",
          b["lower"] < b["upper"], detail=str(b))


if __name__ == "__main__":
    test_parse_clean()
    test_parse_rejects_malformed()
    test_pct_under_50ms_full_capture()
    test_mean_fps_full_capture()
    test_steady_stall_rate_counts_only_t_ge_15()
    test_steady_stall_rate_reports_exact_zero_when_none_qualify()
    test_clusters_merges_within_1s_and_splits_beyond_it()
    test_clusters_does_not_merge_everything()
    test_steady_stall_bounds_exact_matches_steady_stall_rate_when_nothing_evicted()
    test_steady_stall_bounds_reports_bounded_when_big_is_truncated()
    print()
    if fails:
        raise SystemExit(f"{fails} check(s) FAILED")
    print("all checks passed")
