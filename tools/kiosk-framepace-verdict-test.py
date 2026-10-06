#!/usr/bin/env python3
"""Self-test for kiosk-framepace-verdict.py, the cross-record smoothness verdict
over N kiosk-framepace records (team-lead's brief, derived from the approved
plan's range rule: "worse direction only; the candidate's worst run vs the
baseline max (stall) / min (% <50 ms, fps)"). Run by hand -- not yet wired into
just guards or ci-guards.sh.

    kiosk-framepace-verdict-test.py    -- every case, both directions

THE CONTRACT THIS PINS, since kiosk-framepace-verdict.py does not exist yet and
this test is what fixes its shape:

    framepace_verdict(baseline_records, candidate_records) -> dict

baseline_records / candidate_records: each a list of records, where a record is
itself the list of raw text lines kiosk-framepace.py's analyze() takes (a P
block + a framepace record -- see kiosk-framepace-test.py's own module
docstring). The function calls analyze() on every record itself (reusing it, not
reimplementing); it is this test's own design that the pure function takes
already-loaded lines rather than file paths, matching kiosk-perf-verdict.py's
own perf_verdict(lines, ...) shape -- file reading is the CLI's job.

rc 2 (could not tell), reasons non-empty, NO "ranges"/"improvements" keys, in
ANY of (team-lead's brief, verbatim):
  - any record isn't rc 0 (per its own analyze() result);
  - baseline and candidate don't each have >= 3 records;
  - a group mixes engines -- read here as: baseline_records must ALL analyze as
    engine "X" and candidate_records must ALL analyze as engine "WPE" ("Baseline
    = engine X records, candidate = engine WPE" is this test's reading of that
    assignment as a per-group homogeneity + role check, not an auto-partition of
    one flat list -- flagged for review, same as the two framepace-analyzer
    judgment calls team-lead already accepted);
  - the records (across BOTH groups) don't all share the same host_role.
Otherwise rc 0 or rc 1 (see below), and the dict carries:
  "ranges": {"baseline": {"presented_fps": (min, max), "pct_under_50": (min, max),
             "stall_rate": (min, max)}, "candidate": {...same 3 keys...}}
  "improvements": [metric names where the candidate's worst beats the baseline's
                    best -- see below]
  -- this return shape (plain Python tuples/lists, these exact key names) is this
  test's own proposal, for review, not spec-fixed; the comparisons themselves are
  not.

Regression (rc 1, reasons naming the metric), checked per metric, worse
direction only -- EACH one compares the candidate's WORST run against the
BASELINE's own WORST run (its max for stall_rate, since higher is worse; its min
for fps/pct_under_50, since lower is worse) -- not the baseline's best:
  - presented_fps:  candidate min < baseline min
  - pct_under_50:   candidate min < baseline min
  - stall_rate:     candidate max > baseline max
rc 0 (reasons == []) if none of the three regress.

"improvements" (informational, never changes rc) fires per metric when the
candidate's WORST beats the baseline's BEST (the opposite extreme from the
regression check):
  - presented_fps:  candidate min > baseline max
  - pct_under_50:   candidate min > baseline max
  - stall_rate:     candidate max < baseline min

CLI: `kiosk-framepace-verdict.py --baseline F [F ...] --candidate F [F ...]`
(this test's own CLI shape, not spec-fixed). Reads each file, builds the two
record-line-lists, prints the per-metric range table (both groups) plus any
"improvement" markers, then the reasons (rc 1) or why it could not tell (rc 2,
following kiosk-perf-verdict.py's own "could not tell: " convention), then exits
with rc.

FIXTURES, how they are built and why (every number below was independently
verified against the real kiosk-framepace.py, not assumed):

Two fixture families, because a single continuous-toggle "every sample is a new
frame" record (kiosk-framepace-test.py's own "steady 60 fps motion" shape) can
only ever show presented_fps close to the declared 60 Hz pacing rate -- useless
for building a baseline/candidate fps RANGE -- while forcing a slower content
rate by simply using a bigger per-sample dt (no filler in between) silently
under-samples the record below the analyzer's own 90%-of-expected gate (the
exact defect impl found and reported against this file's SIBLING,
kiosk-framepace-test.py, on this same branch). The fix used there -- same-hash
filler samples between real frame changes -- is reused here via steady_raw():
every sample lands on an exact DT (~1/60 s) tick, continuous vblank-rate
sampling, and the hash toggles only on every k-th tick, giving an EXACT,
alias-free content rate of (60/k) fps with k real vblank ticks per frame. k=1
gives 60 fps / pct_under_50 100%; k>=3 (period >= 50 ms) gives pct_under_50 0%
cleanly (no partial/aliased intervals -- confirmed for k=1..9 against the real
analyzer before trusting this).

  FPS FAMILY (presented_fps focus; pct_under_50 == 0 and stall_rate == 0 for
  EVERY record in this family, by construction with k >= 3, so neither metric
  can contaminate an fps-only assertion):
    baseline:            k = 6, 5, 4   -> fps 10, 12, 15   range (10, 15)
    candidate, no regr.: k = 4, 3, 6   -> fps 15, 20, 10   min 10, not < 10
    candidate, fps regr: k = 9, 3, 4   -> fps 6.67, 20, 15 min 6.67 < 10
    candidate, improve:  k = 3, 3, 3   -> fps 20 each       min 20 > baseline max 15

  QUALITY FAMILY (pct_under_50 / stall_rate focus; presented_fps stays >= 59 and
  pct_under_50 == 100 for every record EXCEPT the one deliberate anomaly in each
  case, confirmed below, so fps never also regresses by accident):
    baseline:            k = 1, 2, 2   -> fps 60, 30, 30, pct 100 throughout, no
                          stalls. range: fps (30, 60), pct (100, 100), stall (0, 0)
    candidate, pct regr: one record = a clean 120-sample ~60 fps block, ONE
                          60 ms gap (steady_with_gap -- motion: < 1.5 s, not a
                          stall: <= 250 ms), then another clean 120-sample
                          block -- fps 59.354, pct 99.58 (the one non-zero
                          interval), no stall -- plus two clean k=1 (60 fps,
                          pct 100) records. Candidate pct min 99.58 < baseline
                          pct min 100; candidate fps min 59.354 is still >=
                          baseline fps min 30 (no fps regression); stall
                          untouched.
    candidate, stall regr: one record = the same clean-120/gap/clean-120 shape
                          with a 2.6 s hold instead (excess 600 ms > 250 ms ->
                          one stall; a HOLD interval is excluded from "motion"
                          entirely, so fps == 60.000 and pct == 100.000 exactly,
                          confirmed, untouched) -- plus two clean k=1 records.
                          Candidate stall_rate max 8.57 > baseline stall_rate
                          max 0; fps/pct both clean (60 is NOT > baseline's own
                          max of 60, so this also does not flag an accidental
                          fps "improvement").
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

PASS, FAIL = [], []


def case(name, got, want):
    (PASS if got == want else FAIL).append(name)
    if got != want:
        print(f"FAIL  {name}\n        want {want!r}\n        got  {got!r}")


def close(name, got, want, tol=1e-6):
    ok = abs(got - want) <= tol * max(1.0, abs(want))
    (PASS if ok else FAIL).append(name)
    if not ok:
        print(f"FAIL  {name}\n        want {want!r} (+/- {tol})\n        got  {got!r}")


def close_range(name, got, want, tol=1e-6):
    close(f"{name} min", got[0], want[0], tol)
    close(f"{name} max", got[1], want[1], tol)


def load(name):
    """A tool, imported by path: the filename is not a module name."""
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fptest = load("kiosk-framepace-test")  # fixture builders only; fptest.fp stays None
                                        # (never called) since this file never
                                        # calls kiosk-framepace.py's analyze()
                                        # directly -- the verdict module does
                                        # that internally.
verdict = load("kiosk-framepace-verdict")

DT = fptest.DT


# -------------------------------------------------------------- record building

def steady_raw(k, n_frames=60, fb_id=101):
    """n_frames presented frames, each exactly k*DT ns after the last, with
    same-hash filler samples at every intervening DT tick (continuous vblank-
    rate sampling; content changing once every k vblanks, exactly). k is an
    integer >= 1 so every frame period is an EXACT multiple of the sampling
    tick -- no quantization/aliasing in the resulting intervals (verified
    against the real analyzer for k = 1..9 before trusting this).

    Returns (lines, raw) in kiosk-framepace-test.py's own (lines, raw) shape."""
    t = 0
    seq = 0
    hash_val = 0
    raw = [(0, 0, 0)]
    for _ in range(n_frames):
        for i in range(k):
            t += DT
            seq += 1
            if i == k - 1:
                hash_val ^= 1
            raw.append((t, hash_val, seq))
    lines = [f"S {ts} {fb_id} {h:016x} {s}" for ts, h, s in raw]
    return lines, raw


def steady(engine, k, host_role="bench", mode=None):
    """One record (kiosk-framepace-test.py's own build_record/p_lines, with
    steady_raw's sample lines) at exactly 60/k fps. Returns (lines, want), where
    want is fptest.expected_metrics() applied to this record's own raw
    presented-frame intervals -- the same oracle kiosk-framepace-test.py
    trusts, not a call to kiosk-framepace.py's analyze()."""
    sample_lines, raw = steady_raw(k)
    kwargs = {"mode": mode} if mode is not None else {}
    lines, seconds, _ = fptest.build_record(
        None, sample_lines=sample_lines,
        p_kwargs={"engine": engine, "host_role": host_role}, **kwargs)
    deltas = fptest.presented_deltas_s(raw)
    want = fptest.expected_metrics(deltas, seconds)
    return lines, want


def steady_with_gap(engine, gap_ns, host_role="bench"):
    """A clean 120-sample ~60 fps steady-motion block, one extra gap of gap_ns
    (via the "hold" item kind: same-hash filler, then a toggle exactly gap_ns
    later -- kiosk-framepace-test.py's own mechanism, which carries no 1.5 s
    assumption of its own), then ANOTHER clean 120-sample block -- large enough
    on both sides that motion time clears the record's own 50%-of-window gate
    even against a multi-second gap (the asymmetric 120/5 split this used
    earlier failed exactly that gate for the 2.6 s case; fixed by matching
    kiosk-framepace-test.py's own proven-good hold fixtures, which use 120 on
    both sides)."""
    spec = [("motion", 120, DT), ("hold", gap_ns, DT), ("motion", 120, DT)]
    lines, seconds, raw = fptest.build_record(
        spec, p_kwargs={"engine": engine, "host_role": host_role})
    deltas = fptest.presented_deltas_s(raw)
    want = fptest.expected_metrics(deltas, seconds)
    return lines, want


def lines_only(built):
    return built[0]


def group_range(records, key):
    vals = [r[1][key] for r in records]
    return (min(vals), max(vals))


# ----------------------------------------------------------------- rc 0 cases

BASELINE_FPS = [steady("X", k) for k in (6, 5, 4)]            # fps 10, 12, 15
BASELINE_FPS_LINES = [lines_only(r) for r in BASELINE_FPS]
BASELINE_FPS_RANGE = group_range(BASELINE_FPS, "presented_fps")

BASELINE_QUALITY = [steady("X", k) for k in (1, 2, 2)]         # fps 60, 30, 30
BASELINE_QUALITY_LINES = [lines_only(r) for r in BASELINE_QUALITY]
BASELINE_QUALITY_PCT_RANGE = group_range(BASELINE_QUALITY, "pct_under_50")
BASELINE_QUALITY_STALL_RANGE = group_range(BASELINE_QUALITY, "stall_rate")


def rc0_cases():
    # No regression: candidate's worst in every metric stays at-or-above (fps)
    # the baseline's own worst, with pct_under_50 and stall_rate untouched (0
    # on both sides, by this family's own construction).
    candidate = [steady("WPE", k) for k in (4, 3, 6)]          # fps 15, 20, 10
    got = verdict.framepace_verdict(BASELINE_FPS_LINES, [lines_only(r) for r in candidate])
    case("no regression: rc 0", got["rc"], 0)
    case("no regression: reasons empty", got["reasons"], [])
    close_range("no regression: baseline presented_fps range",
                got["ranges"]["baseline"]["presented_fps"], BASELINE_FPS_RANGE)
    close_range("no regression: candidate presented_fps range",
                got["ranges"]["candidate"]["presented_fps"], group_range(candidate, "presented_fps"))
    case("no regression: no improvements flagged", got["improvements"], [])

    # Improvement: the candidate's worst fps (20) clearly beats the baseline's
    # best fps (15) -- flagged, but NOT a regression (still rc 0): the
    # candidate's worst (20) is also still >= the baseline's worst (10).
    candidate = [steady("WPE", 3), steady("WPE", 3), steady("WPE", 3)]  # fps 20 each
    got = verdict.framepace_verdict(BASELINE_FPS_LINES, [lines_only(r) for r in candidate])
    case("improvement: rc 0 (an improvement is not a regression)", got["rc"], 0)
    case("improvement: presented_fps flagged as an improvement",
         "presented_fps" in got["improvements"], True)
    case("improvement: pct_under_50 NOT flagged (0 does not beat 0)",
         "pct_under_50" in got["improvements"], False)


# ----------------------------------------------------------------- rc 1 cases

def rc1_cases():
    # fps regression, isolated: one candidate record's fps (6.67) undercuts
    # the baseline's own worst (10); pct_under_50 and stall_rate are 0 on
    # every record in this family, so neither can also regress.
    candidate = [steady("WPE", k) for k in (9, 3, 4)]          # fps 6.67, 20, 15
    got = verdict.framepace_verdict(BASELINE_FPS_LINES, [lines_only(r) for r in candidate])
    case("fps regression: rc 1", got["rc"], 1)
    case("fps regression: reasons name presented_fps",
         any("presented_fps" in r or "fps" in r for r in got["reasons"]), True)
    close("fps regression: candidate presented_fps min",
          got["ranges"]["candidate"]["presented_fps"][0], 20 / 3)

    # pct_under_50 regression, isolated (quality family): one candidate
    # record has a single 60 ms gap, dragging ONLY its own pct_under_50
    # (99.58 %) under the baseline's worst (100 %); its fps (59.35) stays
    # above the baseline's worst (30) and it has no stall (confirmed above).
    gap_rec = steady_with_gap("WPE", 60_000_000)
    candidate = [gap_rec, steady("WPE", 1), steady("WPE", 1)]
    got = verdict.framepace_verdict(
        BASELINE_QUALITY_LINES, [lines_only(gap_rec)] + [lines_only(steady("WPE", 1)) for _ in range(2)])
    case("pct_under_50 regression: rc 1", got["rc"], 1)
    case("pct_under_50 regression: reasons name pct_under_50",
         any("pct_under_50" in r for r in got["reasons"]), True)
    close("pct_under_50 regression: candidate pct_under_50 min",
          got["ranges"]["candidate"]["pct_under_50"][0], gap_rec[1]["pct_under_50"])
    case("pct_under_50 regression: fps did NOT also regress",
         any("presented_fps" in r or "fps" in r for r in got["reasons"]), False)
    case("pct_under_50 regression: stall_rate did NOT also regress",
         any("stall_rate" in r or "stall" in r for r in got["reasons"]), False)

    # stall_rate regression, isolated (quality family): one candidate record
    # carries a 2.6 s hold (600 ms edge excess -> one stall). A HOLD interval
    # is excluded from "motion" entirely, so this record's fps (60.000) and
    # pct_under_50 (100.000) are untouched (confirmed above) -- only
    # stall_rate can regress here.
    hold_rec = steady_with_gap("WPE", 2_600_000_000)
    candidate_lines = [lines_only(hold_rec)] + [lines_only(steady("WPE", 1)) for _ in range(2)]
    got = verdict.framepace_verdict(BASELINE_QUALITY_LINES, candidate_lines)
    case("stall_rate regression: rc 1", got["rc"], 1)
    case("stall_rate regression: reasons name stall_rate",
         any("stall_rate" in r or "stall" in r for r in got["reasons"]), True)
    close("stall_rate regression: candidate stall_rate max",
          got["ranges"]["candidate"]["stall_rate"][1], hold_rec[1]["stall_rate"])
    case("stall_rate regression: fps did NOT also regress",
         any("presented_fps" in r or "fps" in r for r in got["reasons"]), False)
    case("stall_rate regression: pct_under_50 did NOT also regress",
         any("pct_under_50" in r for r in got["reasons"]), False)


# ----------------------------------------------------------------- rc 2 cases

def rc2_cases():
    good_candidate_lines = [lines_only(steady("WPE", k)) for k in (4, 3, 6)]

    # A record that isn't rc 0 on its own (wrong mode) poisons the whole
    # verdict, even though the other two baseline records are fine and the
    # candidate group is entirely clean.
    bad_mode_lines, _ = steady("X", 6, mode="1920x1080@60")
    baseline_lines = [lines_only(steady("X", 6)), lines_only(steady("X", 5)), bad_mode_lines]
    got = verdict.framepace_verdict(baseline_lines, good_candidate_lines)
    case("a non-rc0 record: rc 2", got["rc"], 2)
    case("a non-rc0 record: reasons non-empty", len(got["reasons"]) > 0, True)
    case("a non-rc0 record: no ranges key on rc 2", "ranges" in got, False)
    case("a non-rc0 record: no improvements key on rc 2", "improvements" in got, False)

    # Fewer than 3 baseline records (candidate is a clean group of 3).
    short_baseline_lines = [lines_only(steady("X", 6)), lines_only(steady("X", 5))]
    got = verdict.framepace_verdict(short_baseline_lines, good_candidate_lines)
    case("baseline under 3 records: rc 2", got["rc"], 2)
    case("baseline under 3 records: reasons non-empty", len(got["reasons"]) > 0, True)

    # A group mixes engines: the baseline group (meant to be all engine "X")
    # has one record that actually analyzes as "WPE".
    mixed_baseline_lines = [lines_only(steady("X", 6)), lines_only(steady("X", 5)),
                             lines_only(steady("WPE", 4))]
    got = verdict.framepace_verdict(mixed_baseline_lines, good_candidate_lines)
    case("baseline group mixes engines: rc 2", got["rc"], 2)
    case("baseline group mixes engines: reasons non-empty", len(got["reasons"]) > 0, True)

    # Records don't all share the same host_role: one candidate record is
    # "prod" while the rest (both groups) are "bench".
    mixed_role_candidate_lines = [lines_only(steady("WPE", 4)),
                                   lines_only(steady("WPE", 3, host_role="prod")),
                                   lines_only(steady("WPE", 6))]
    got = verdict.framepace_verdict(BASELINE_FPS_LINES, mixed_role_candidate_lines)
    case("different host_role values: rc 2", got["rc"], 2)
    case("different host_role values: reasons non-empty", len(got["reasons"]) > 0, True)


# ------------------------------------------------------------------- CLI

def cli_cases(tmp_path):
    tmp = Path(tmp_path)

    def write_group(prefix, records_lines):
        paths = []
        for i, lines in enumerate(records_lines):
            p = tmp / f"{prefix}{i}.rec"
            p.write_text("\n".join(lines) + "\n")
            paths.append(str(p))
        return paths

    baseline_paths = write_group("baseline", BASELINE_FPS_LINES)
    ok_candidate_lines = [lines_only(steady("WPE", k)) for k in (4, 3, 6)]
    candidate_paths = write_group("candidate", ok_candidate_lines)

    got = subprocess.run(
        [sys.executable, str(TOOLS / "kiosk-framepace-verdict.py"),
         "--baseline", *baseline_paths, "--candidate", *candidate_paths],
        capture_output=True, text=True)
    case("CLI: no-regression group exits 0", got.returncode, 0)
    case("CLI: prints the presented_fps metric name", "presented_fps" in got.stdout, True)

    reg_candidate_lines = [lines_only(steady("WPE", k)) for k in (9, 3, 4)]
    reg_paths = write_group("regress", reg_candidate_lines)
    got = subprocess.run(
        [sys.executable, str(TOOLS / "kiosk-framepace-verdict.py"),
         "--baseline", *baseline_paths, "--candidate", *reg_paths],
        capture_output=True, text=True)
    case("CLI: fps-regression group exits 1", got.returncode, 1)


def main() -> int:
    rc0_cases()
    rc1_cases()
    rc2_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cli_cases(tmp)
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
