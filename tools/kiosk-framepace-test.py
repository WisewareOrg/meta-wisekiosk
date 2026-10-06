#!/usr/bin/env python3
"""Self-test for kiosk-framepace.py, the host analyzer for the kiosk-framepace device
tool's record. Run by hand -- not yet wired into just guards or ci-guards.sh.

    kiosk-framepace-test.py    -- every case, both directions

THE CONTRACT THIS PINS, since kiosk-framepace.py does not exist yet and this test is
what fixes its shape (framepace-spec.md section "Host analyzer" for the analysis
rules; section "Record format" -- agreed with impl 2026-10-06 -- for the record
fixtures build below):

    H tool=<12 hex>                (compiled-in sha256 prefix; opaque to the analyzer)
    H mode=1280x720@<vrefresh>
    H pacing=vblank | H pacing=timer100 <reason>
    H regions=x70-325,434-688;y303,326,350,388,411,522,545,568,607,630;step1
    H start=<YYYY-MM-DDTHH:MM:SSZ>
    H seconds=<N>
    S <t_ns> <fb_id> <hash16> <seq>     -- one per sample; seq decimal, or "-" under timer100
    ...
    H cpu_ms=<int>
    H samples=<n> missed=<n> end=<YYYY-MM-DDTHH:MM:SSZ>   -- always the LAST line

A run that exits early (any failure, signal) writes NEITHER footer line -- the two
are atomic, both or neither, never just one.

THIS ANALYZER'S OWN CONTRACT -- its output shape and the stall_rate window
denominator are not fixed by the spec and are this test's proposal, for review:

    analyze(lines) -> dict

lines: a record's raw text lines in the format above.

Returns {"rc": 0|2, "reasons": [str, ...]}; on rc 0 the dict also carries
"presented_fps", "pct_under_50", "stalls", "stall_rate", "max_stall_ms".

Processing, straight from the spec:
  - A presented frame is a sample whose hash differs from the PREVIOUS SAMPLE's (not
    the previous presented frame). The first sample in the record has no previous
    sample and is never itself classified.
  - Intervals are the time between consecutive presented frames (so the record's
    very first presented frame starts no interval of its own -- an interval needs
    two of them).
  - Hold rule: interval >= 1.5 s is a hold; its excess = interval - 2.0 s, and an
    excess > 0.25 s is one stall of that excess size (a stall at the hold edge).
    interval < 1.5 s is a motion interval; one > 0.25 s is one stall of that
    interval's own size.
  - presented_fps and pct_under_50 are computed over motion intervals only:
    presented_fps = (count of motion intervals) / (their summed duration) --
    "motion frames" is this count, since the first sample of any run is
    structurally unclassifiable and every other one pairs 1:1 with the interval
    that produced it, so "frames" and "intervals" name the same count here.
    pct_under_50 = 100 * (motion intervals < 50 ms) / (all motion intervals).
  - stalls = count of motion-interval stalls + hold-edge stalls (as defined above).
    max_stall_ms = the largest stall size in ms (0.0 if there are none).
  - stall_rate = stalls / (DECLARED window minutes, from the record's own `H
    seconds=<N>`) -- the spec's "Host analyzer" wording deliberately shifts from
    "motion seconds" (fps's denominator) to "window minutes" for this one metric,
    so it is NOT restricted to motion time. This denominator is this test's own
    proposal (flagged above), not spec-fixed.
  - rc 2 (could not tell), reasons non-empty, NO other keys in the dict, in ANY of:
      - a required header field is missing (probed here with `seconds`, since it is
        unambiguously needed to compute anything -- distinct from the "wrong mode"
        case below, which is a PRESENT but wrong `mode` value);
      - there is no `H samples=... end=...` trailer line at all (an early exit --
        per the record format, `cpu_ms` is then absent too, since the footer is
        atomic);
      - the record's actual sample count (the number of `S` lines actually present,
        independent of any self-reported count) is under 90 % of the expected count
        for the declared window and pacing (seconds * refresh for pacing=vblank,
        using the refresh parsed out of `H mode=<w>x<h>@<refresh>`);
      - motion seconds (summed motion-interval duration) is under 50 % of the
        declared window;
      - the declared mode is not exactly 1280x720 (any refresh).
    Otherwise rc 0, reasons == [], and the metrics above are printed/returned.
  CLI: `kiosk-framepace.py <record>`. Prints the metrics (rc 0) or, following this
  tool family's own kiosk-perf-verdict.py convention, each reason prefixed "could
  not tell: " (rc 2), then exits with rc. The exact stdout wording beyond that is
  this test's own design, not spec-fixed -- only rc and substantive content are
  checked below.

Fixtures are synthetic device-tool records built from first principles (a sample
list derived from a small (motion|hold) segment spec, see gen_raw_samples below),
not reconstructed from any real capture -- the device tool does not exist yet
either. Expected metric values come from expected_metrics(), a small oracle that
transcribes the spec clauses above directly against the SAME presented-frame
interval list the fixture was built from -- not from calling kiosk-framepace.py.
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


def load(name):
    """kiosk-framepace.py, imported by path: the filename is not a module name."""
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fp = load("kiosk-framepace")

DT = 16_666_667          # ns/sample at ~60 Hz -- the pacing rate used by every fixture
REFRESH = 60
MODE = f"1280x720@{REFRESH}"


# -------------------------------------------------------------- record building

def gen_raw_samples(spec, fb_id=101):
    """spec: a list of ("motion", n, dt_ns) | ("hold", gap_ns, filler_dt_ns) items.

    "motion" appends n samples, each with a freshly toggled hash, dt_ns apart (every
    one a presented frame by the "differs from the previous SAMPLE" rule).

    "hold" appends same-hash filler samples (not presented frames) spaced filler_dt_ns
    apart, advancing time so that the FOLLOWING spec item's first appended sample --
    which must be a "motion" item -- lands exactly gap_ns after this hold's last real
    (motion) sample. That is the hold's one measured interval.

    seq increments by exactly 1 every sample (vblank pacing, no missed vblanks), so
    every fixture's footer can truthfully declare missed=0.

    Returns (lines, raw) where raw is [(t_ns, hash_int, seq), ...] in order and lines
    are this record's "S <t_ns> <fb_id> <hash16> <seq>" lines.
    """
    t = 0
    hash_val = 0
    seq = 0
    raw = [(t, hash_val, seq)]  # the record's first sample: never itself classified
    for idx, item in enumerate(spec):
        kind = item[0]
        if kind == "motion":
            _, n, dt = item
            for _ in range(n):
                t += dt
                hash_val ^= 1
                seq += 1
                raw.append((t, hash_val, seq))
        elif kind == "hold":
            _, gap_ns, filler_dt = item
            hold_start = t
            target = hold_start + gap_ns
            nxt = spec[idx + 1]
            if nxt[0] != "motion":
                raise ValueError("a hold item must be followed by a motion item")
            next_dt = nxt[2]
            while t + filler_dt < target - next_dt:
                t += filler_dt
                seq += 1
                raw.append((t, hash_val, seq))
            t = target - next_dt  # the next item's first "t += dt; append" lands on target
        else:
            raise ValueError(kind)
    lines = [f"S {ts} {fb_id} {h:016x} {s}" for ts, h, s in raw]
    return lines, raw


def presented_deltas_s(raw):
    """framepace-spec.md "Host analyzer": "Presented frame = a sample whose hash
    differs from the previous sample's. Intervals = time between consecutive
    presented frames." Computed directly from the raw (t, hash, seq) series,
    independent of kiosk-framepace.py."""
    frame_times = [t for (pt, ph, ps), (t, h, s) in zip(raw[:-1], raw[1:]) if h != ph]
    return [(b - a) / 1e9 for a, b in zip(frame_times, frame_times[1:])]


def expected_metrics(deltas_s, window_seconds):
    """The oracle: framepace-spec.md's "Hold rule" and "Metrics" clauses applied
    directly to a presented-frame interval list. See this file's module docstring
    for the exact wording each line below transcribes."""
    motion = [d for d in deltas_s if d < 1.5]
    holds = [d for d in deltas_s if d >= 1.5]
    stall_sizes_ms = [d * 1000 for d in motion if d > 0.25]
    stall_sizes_ms += [(d - 2.0) * 1000 for d in holds if (d - 2.0) > 0.25]
    motion_seconds = sum(motion)
    return {
        "motion_seconds": motion_seconds,
        "presented_fps": len(motion) / motion_seconds,
        "pct_under_50": 100.0 * sum(1 for d in motion if d < 0.050) / len(motion),
        "stalls": len(stall_sizes_ms),
        "max_stall_ms": max(stall_sizes_ms) if stall_sizes_ms else 0.0,
        "stall_rate": len(stall_sizes_ms) / (window_seconds / 60.0),
    }


REGIONS = "x70-325,434-688;y303,326,350,388,411,522,545,568,607,630;step1"


def header_lines(seconds, mode=MODE, pacing="vblank", omit=()):
    fields = [
        ("tool", "a1b2c3d4e5f6"),  # 12 hex, as framepace-spec.md's record format requires
        ("mode", mode),
        ("pacing", pacing),
        ("regions", REGIONS),
        ("start", "2026-10-06T00:00:00Z"),
        ("seconds", str(seconds)),
    ]
    return [f"H {k}={v}" for k, v in fields if k not in omit]


def trailer_lines(n_samples, missed=0, end="2026-10-06T00:00:08Z", cpu_ms=40, omit_end=False):
    """cpu_ms before samples=/missed=/end=, which is always the record's last line --
    framepace-spec.md's record format, agreed with impl 2026-10-06. The two lines are
    atomic (an early exit writes neither), so omit_end drops both."""
    if omit_end:
        return []
    return [f"H cpu_ms={cpu_ms}",
            f"H samples={n_samples} missed={missed} end={end}"]


def build_record(spec, seconds=None, mode=MODE, pacing="vblank", omit_header=(),
                  omit_end=False, sample_lines=None):
    """Assembles a full record's lines. seconds defaults to the ROUNDED actual
    elapsed span of the generated samples (declared window == observed window, so
    a test is never accidentally exercising the "declared vs observed" question
    this fixture is not about)."""
    if sample_lines is None:
        sample_lines, raw = gen_raw_samples(spec)
    else:
        raw = None
    if seconds is None:
        last_t = int(sample_lines[-1].split()[1])
        seconds = round(last_t / 1e9)
    lines = (header_lines(seconds, mode=mode, pacing=pacing, omit=omit_header)
             + sample_lines
             + trailer_lines(len(sample_lines), omit_end=omit_end))
    return lines, seconds, raw


# ----------------------------------------------------------------- rc 0 cases

def rc0_cases():
    # Steady 60 fps motion: every sample toggles, so every interval is a motion
    # interval of exactly DT -- no stalls, pct_under_50 == 100 (DT << 50 ms).
    spec = [("motion", 120, DT)]
    lines, seconds, raw = build_record(spec)
    deltas = presented_deltas_s(raw)
    want = expected_metrics(deltas, seconds)
    got = fp.analyze(lines)
    case("steady 60 fps motion: rc 0", got["rc"], 0)
    case("steady 60 fps motion: reasons empty", got["reasons"], [])
    close("steady 60 fps motion: presented_fps", got["presented_fps"], want["presented_fps"])
    close("steady 60 fps motion: pct_under_50", got["pct_under_50"], want["pct_under_50"])
    case("steady 60 fps motion: stalls", got["stalls"], 0)
    close("steady 60 fps motion: max_stall_ms", got["max_stall_ms"], 0.0)
    close("steady 60 fps motion: stall_rate", got["stall_rate"], 0.0)

    # Motion with mid-motion stalls: two isolated gaps (300 ms, 400 ms), both
    # still < 1.5 s so both are motion intervals, both > 250 ms so both are
    # stalls -- a fencepost-free fixture (no holds) so "motion frames" is
    # unambiguous here too.
    spec = [("motion", 20, DT), ("motion", 1, 300_000_000),
            ("motion", 20, DT), ("motion", 1, 400_000_000),
            ("motion", 20, DT)]
    lines, seconds, raw = build_record(spec)
    deltas = presented_deltas_s(raw)
    want = expected_metrics(deltas, seconds)
    got = fp.analyze(lines)
    case("motion with mid-motion stalls: rc 0", got["rc"], 0)
    close("motion with mid-motion stalls: presented_fps", got["presented_fps"], want["presented_fps"])
    close("motion with mid-motion stalls: pct_under_50", got["pct_under_50"], want["pct_under_50"])
    case("motion with mid-motion stalls: stalls == 2", got["stalls"], 2)
    close("motion with mid-motion stalls: max_stall_ms == 400", got["max_stall_ms"], 400.0)
    close("motion with mid-motion stalls: stall_rate", got["stall_rate"], want["stall_rate"])

    # A hold of exactly 2.0 s: excess == 0, not > 0.25 -- no stall.
    spec = [("motion", 60, DT), ("hold", 2_000_000_000, DT), ("motion", 60, DT)]
    lines, seconds, raw = build_record(spec)
    deltas = presented_deltas_s(raw)
    hold_deltas = [d for d in deltas if d >= 1.5]
    case("hold of exactly 2.0s: the fixture actually produced one hold interval",
         len(hold_deltas), 1)
    close("hold of exactly 2.0s: that interval is 2.000 s", hold_deltas[0], 2.0, tol=1e-9)
    got = fp.analyze(lines)
    case("hold of exactly 2.0s: rc 0", got["rc"], 0)
    case("hold of exactly 2.0s: stalls == 0 (no stall at the edge)", got["stalls"], 0)
    close("hold of exactly 2.0s: max_stall_ms == 0", got["max_stall_ms"], 0.0)

    # A hold of 2.6 s: excess == 0.6 s == 600 ms > 0.25 s -- one stall, sized
    # by the excess, not by the hold's own 2.6 s length.
    spec = [("motion", 60, DT), ("hold", 2_600_000_000, DT), ("motion", 60, DT)]
    lines, seconds, raw = build_record(spec)
    deltas = presented_deltas_s(raw)
    hold_deltas = [d for d in deltas if d >= 1.5]
    case("hold of 2.6s: the fixture actually produced one hold interval",
         len(hold_deltas), 1)
    close("hold of 2.6s: that interval is 2.600 s", hold_deltas[0], 2.6, tol=1e-9)
    got = fp.analyze(lines)
    case("hold of 2.6s: rc 0", got["rc"], 0)
    case("hold of 2.6s: stalls == 1 (one edge stall)", got["stalls"], 1)
    close("hold of 2.6s: max_stall_ms == 600 (the excess, not 2600)", got["max_stall_ms"], 600.0)

    # An interval of 1.4 s: < 1.5 s, so a MOTION interval, not a hold -- its
    # whole 1400 ms counts as the stall size (no excess subtraction), and a
    # wrong-threshold implementation that misclassified it as a hold would see
    # excess = 1.4 - 2.0 = -0.6, not > 0.25, i.e. stalls == 0 instead of 1.
    spec = [("motion", 60, DT), ("motion", 1, 1_400_000_000), ("motion", 60, DT)]
    lines, seconds, raw = build_record(spec)
    deltas = presented_deltas_s(raw)
    motion_stall_deltas = [d for d in deltas if 1.5 > d > 0.25]
    case("interval of 1.4s: the fixture actually produced one such motion interval",
         len(motion_stall_deltas), 1)
    close("interval of 1.4s: that interval is 1.400 s", motion_stall_deltas[0], 1.4, tol=1e-9)
    got = fp.analyze(lines)
    case("interval of 1.4s: rc 0", got["rc"], 0)
    case("interval of 1.4s: stalls == 1 (classified motion, not a hold)", got["stalls"], 1)
    close("interval of 1.4s: max_stall_ms == 1400 (the full interval)", got["max_stall_ms"], 1400.0)


# ----------------------------------------------------------------- rc 2 cases

def rc2_cases():
    base_spec = [("motion", 120, DT)]

    # A required header field is missing (seconds): isolated from the "wrong
    # mode" case below by picking a field OTHER than mode.
    lines, seconds, raw = build_record(base_spec, omit_header=("seconds",))
    got = fp.analyze(lines)
    case("missing header field (seconds): rc 2", got["rc"], 2)
    case("missing header field (seconds): reasons non-empty", len(got["reasons"]) > 0, True)
    case("missing header field (seconds): no metric keys on rc 2",
         "presented_fps" in got, False)

    # No end line at all (an early exit) -- plenty of samples, so this is
    # isolated from the "too few samples" case below.
    lines, seconds, raw = build_record(base_spec, omit_end=True)
    got = fp.analyze(lines)
    case("no end line: rc 2", got["rc"], 2)
    case("no end line: reasons non-empty", len(got["reasons"]) > 0, True)

    # Too few samples: a declared 8 s / 60 Hz window expects 480 samples;
    # 50 sparse-but-continuously-toggling samples is far under 90% of that
    # (432), while motion_seconds still covers nearly the whole declared
    # window (so this is isolated from the "motion under 50%" case below).
    sparse_spec = [("motion", 50, 160_000_000)]  # 50 samples, 160 ms apart, ~8s span
    sample_lines, raw = gen_raw_samples(sparse_spec)
    lines, seconds, _ = build_record(None, seconds=8, sample_lines=sample_lines)
    got = fp.analyze(lines)
    case("too few samples: rc 2", got["rc"], 2)
    case("too few samples: reasons non-empty", len(got["reasons"]) > 0, True)

    # Motion under 50% of the window: a long hold dwarfs two short motion runs
    # either side of it, well-sampled throughout (dense filler during the
    # hold) so this is isolated from the "too few samples" case above.
    void_spec = [("motion", 10, DT), ("hold", 7_000_000_000, DT), ("motion", 10, DT)]
    lines, seconds, raw = build_record(void_spec)
    deltas = presented_deltas_s(raw)
    motion_fraction = sum(d for d in deltas if d < 1.5) / seconds
    case("motion under 50%: the fixture actually is under 50% motion",
         motion_fraction < 0.5, True)
    got = fp.analyze(lines)
    case("motion under 50%: rc 2", got["rc"], 2)
    case("motion under 50%: reasons non-empty", len(got["reasons"]) > 0, True)

    # The wrong mode: otherwise identical to the rc-0 steady-motion fixture.
    lines, seconds, raw = build_record(base_spec, mode="1920x1080@60")
    got = fp.analyze(lines)
    case("wrong mode: rc 2", got["rc"], 2)
    case("wrong mode: reasons non-empty", len(got["reasons"]) > 0, True)


# ------------------------------------------------------------------- CLI

def cli_cases(tmp_path):
    tmp = Path(tmp_path)

    ok_lines, _, _ = build_record([("motion", 120, DT)])
    ok_capture = tmp / "ok.txt"
    ok_capture.write_text("\n".join(ok_lines) + "\n")
    got = subprocess.run([sys.executable, str(TOOLS / "kiosk-framepace.py"), str(ok_capture)],
                          capture_output=True, text=True)
    case("CLI: rc 0 capture exits 0", got.returncode, 0)
    case("CLI: rc 0 capture prints the fps metric", "presented_fps" in got.stdout, True)

    bad_lines, _, _ = build_record([("motion", 120, DT)], mode="1920x1080@60")
    bad_capture = tmp / "bad.txt"
    bad_capture.write_text("\n".join(bad_lines) + "\n")
    got = subprocess.run([sys.executable, str(TOOLS / "kiosk-framepace.py"), str(bad_capture)],
                          capture_output=True, text=True)
    case("CLI: wrong-mode capture exits 2", got.returncode, 2)
    case("CLI: wrong-mode capture says it could not tell (this tool family's own "
         "kiosk-perf-verdict.py convention)", "could not tell" in got.stdout.lower(), True)


def main() -> int:
    rc0_cases()
    rc2_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cli_cases(tmp)
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
