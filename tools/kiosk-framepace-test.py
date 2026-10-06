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

A record is actually `P key=value` lines (the driver's provenance block,
framepace-spec.md section "Driver", points 2/4/5) followed by the framepace
record above. rc 2, additionally, in ANY of:
      - a required `P` key is missing OR present with an empty value. Required:
        tools_commit, host_role, buildinfo_wisekiosk, slot, kiosk_conf_sha256,
        kiosk_conf, browser_procs, crtc_state, kiosk_nrestarts_start,
        kiosk_nrestarts_end, boot_id, boot_id_end, uptime_s, screenshot -- plus
        proc_cmdline_<launcher> and proc_environ_<launcher>, where <launcher> is
        NOT a fixed name: it is "surf" when browser_procs names the X server, or
        "wpe-kiosk" when browser_procs names wpe-kiosk (section "Driver" point 2:
        "for the browser launcher (surf or wpe-kiosk)");
      - kiosk_nrestarts_end != kiosk_nrestarts_start, or boot_id_end != boot_id
        (section "Driver" point 4: "A restart or reboot during the run -> rc 2");
      - browser_procs names neither the X server nor wpe-kiosk, or names BOTH --
        the engine cannot be derived either way.
    Otherwise rc 0, reasons == [], the metrics above, AND "engine": "X" or "WPE"
    (wpe-kiosk) are printed/returned. "engine" is this test's own addition to
    analyze()'s output, proposed here for review along with the rest of the
    shape above, per section "Driver" point 6/Output ("Engine is derived (X if
    Xorg is running, WPE if wpe-kiosk is)" -- the spec's own wording, but amended
    here per a bench measurement (team-lead, 2026-10-06): the X image's own
    process is `xinit`/`X`/`surf`/`WebKitNetworkPr`/`WebKitWebProces` (comm
    truncated to 15 chars) -- the X SERVER's comm is the literal string "X", not
    "Xorg", so browser_procs is matched on exact comm "X", not a substring).
  CLI: `kiosk-framepace.py <record>`. Prints the metrics (rc 0) or, following this
  tool family's own kiosk-perf-verdict.py convention, each reason prefixed "could
  not tell: " (rc 2), then exits with rc. The exact stdout wording beyond that is
  this test's own design, not spec-fixed -- only rc and substantive content are
  checked below. The printed metrics are `M key=value` lines, one per metric; a
  record with that CLI's own M lines appended re-analyzes to the IDENTICAL
  result (M lines are parsed and skipped), while any other unrecognised line
  kind is not -- rc 2.

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


fp = None  # set by main() -- see the comment there; a module that only wants the
           # fixture builders below (kiosk-framepace-verdict-test.py) can import
           # this one without tripping over kiosk-framepace.py not existing.

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


def p_lines(engine="X", omit=(), blank=(), nrestarts_end=None, boot_id_end=None,
            host_role="bench"):
    """The driver's provenance block (framepace-spec.md section "Driver", points 2,
    4 and 5): one `P key=value` line per field, read from the device around the
    framepace run.

    engine picks which of the X server (exact comm "X", a bench measurement,
    not "Xorg")/wpe-kiosk browser_procs names (and so which launcher's
    proc_cmdline_/proc_environ_ keys this block carries -- "surf" for X,
    "wpe-kiosk" for WPE itself); "neither"/"both" make browser_procs
    deliberately ambiguous and carry NO launcher keys at all, since nothing then
    names which one would even be required.

    omit drops a key outright; blank keeps it present with an empty value --
    both must read rc 2, "missing or empty". nrestarts_end/boot_id_end default to
    matching their start value (no restart/reboot during the run); passing a
    different value is how the mismatch cases below are built. host_role
    defaults to "bench"; overriding it is how kiosk-framepace-verdict-test.py
    builds its "different host_role values" case.
    """
    boot_id = "4c9e6b1a-boot"
    nrestarts_start = "3"
    if engine == "X":
        # Bench measurement (team-lead, 2026-10-06): the X image's processes
        # are xinit, X (the X server's comm -- "X", not "Xorg"), surf,
        # WebKitNetworkPr, WebKitWebProces (comm truncated to 15 chars).
        browser_procs, launcher = "100:xinit,101:X,102:surf,103:WebKitWebProces,104:WebKitNetworkPr", "surf"
    elif engine == "WPE":
        browser_procs, launcher = "150:wpe-kiosk,151:WebKitWebProcess", "wpe-kiosk"
    elif engine == "neither":
        browser_procs, launcher = "900:bash", None
    elif engine == "both":
        browser_procs, launcher = "101:X,150:wpe-kiosk", None
    else:
        raise ValueError(engine)

    fields = [
        ("tools_commit", "a1b2c3d"),
        ("host_role", host_role),
        ("buildinfo_wisekiosk", "meta-wisekiosk a1b2c3d 2026-10-06"),
        ("slot", "A"),
        ("kiosk_conf_sha256", "a" * 64),
        ("kiosk_conf", "aGVsbG8="),
        ("browser_procs", browser_procs),
        ("crtc_state", "plane-0: fb=42  crtc-0: mode=1280x720"),
        ("kiosk_nrestarts_start", nrestarts_start),
        ("kiosk_nrestarts_end", nrestarts_end if nrestarts_end is not None else nrestarts_start),
        ("boot_id", boot_id),
        ("boot_id_end", boot_id_end if boot_id_end is not None else boot_id),
        ("uptime_s", "12345"),
        ("screenshot", "sha256:" + "f" * 64),
    ]
    if launcher is not None:
        fields += [(f"proc_cmdline_{launcher}", "L3Vzci9iaW4v" + launcher),
                   (f"proc_environ_{launcher}", "SE9NRT0vcm9vdA==")]

    lines = []
    for k, v in fields:
        if k in omit:
            continue
        lines.append(f"P {k}={v if k not in blank else ''}")
    return lines


def build_record(spec, seconds=None, mode=MODE, pacing="vblank", omit_header=(),
                  omit_end=False, sample_lines=None, p_kwargs=None):
    """Assembles a full record's lines: a provenance (P) block, then the
    framepace record. seconds defaults to the ROUNDED actual elapsed span of the
    generated samples (declared window == observed window, so a test is never
    accidentally exercising the "declared vs observed" question this fixture is
    not about). p_kwargs defaults to a fully valid X-engine P block, so every
    case that is NOT about the P block itself still gets rc 0 (or rc 2 for its
    own, isolated, framepace-side reason) through it unmolested; the provenance
    cases below override p_kwargs to inject the one defect under test."""
    if sample_lines is None:
        sample_lines, raw = gen_raw_samples(spec)
    else:
        raw = None
    if seconds is None:
        last_t = int(sample_lines[-1].split()[1])
        seconds = round(last_t / 1e9)
    lines = (p_lines(**(p_kwargs if p_kwargs is not None else {"engine": "X"}))
             + header_lines(seconds, mode=mode, pacing=pacing, omit=omit_header)
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
    # stalls. Built with the "hold" item kind -- which just means "same-hash
    # filler samples, then a toggle exactly gap_ns later" and carries no 1.5 s
    # assumption of its own -- so a real device's continuous vblank sampling
    # through the gap is represented, not skipped (impl finding: the bare
    # one-sample "motion" item this used before left the gap unsampled,
    # failing the record's own 90%-of-expected-samples gate). 120-sample
    # motion blocks keep the fixture dense and large enough that sample count
    # and motion fraction both clear their gates with margin.
    spec = [("motion", 120, DT), ("hold", 300_000_000, DT),
            ("motion", 120, DT), ("hold", 400_000_000, DT),
            ("motion", 120, DT)]
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

    # A hold of exactly 2.0 s: excess == 0, not > 0.25 -- no stall. 120-sample
    # motion blocks (not 60) so motion_seconds (~3.97 s) clears the record's
    # own 50%-of-window motion gate against this 2.0 s hold (impl finding: at
    # 60 samples/block, motion was only ~1.97 s against a ~4 s window, under
    # 50%).
    spec = [("motion", 120, DT), ("hold", 2_000_000_000, DT), ("motion", 120, DT)]
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
    # by the excess, not by the hold's own 2.6 s length. 120-sample motion
    # blocks for the same 50%-of-window reason as the 2.0 s case above.
    spec = [("motion", 120, DT), ("hold", 2_600_000_000, DT), ("motion", 120, DT)]
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
    # Built with "hold" (continuously filler-sampled, same impl finding as
    # above) and 120-sample motion blocks for sample-count margin.
    spec = [("motion", 120, DT), ("hold", 1_400_000_000, DT), ("motion", 120, DT)]
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


# ------------------------------------------------------------ provenance (P) block

def p_block_cases():
    base_spec = [("motion", 120, DT)]

    # rc 0, engine == "X": a fully valid P block (surf launcher) plus the proven
    # rc-0 framepace part.
    lines, seconds, raw = build_record(base_spec, p_kwargs={"engine": "X"})
    got = fp.analyze(lines)
    case("valid P block (X engine): rc 0", got["rc"], 0)
    case("valid P block (X engine): engine == 'X'", got.get("engine"), "X")

    # rc 0, engine == "WPE": same framepace part, a WPE-shaped P block instead.
    lines, seconds, raw = build_record(base_spec, p_kwargs={"engine": "WPE"})
    got = fp.analyze(lines)
    case("valid P block (WPE engine): rc 0", got["rc"], 0)
    case("valid P block (WPE engine): engine == 'WPE'", got.get("engine"), "WPE")

    # A required, engine-independent P key missing outright.
    lines, seconds, raw = build_record(
        base_spec, p_kwargs={"engine": "X", "omit": ("tools_commit",)})
    got = fp.analyze(lines)
    case("missing P key (tools_commit): rc 2", got["rc"], 2)
    case("missing P key (tools_commit): reasons non-empty", len(got["reasons"]) > 0, True)
    case("missing P key (tools_commit): no engine key on rc 2", "engine" in got, False)

    # The same key present but empty -- a different failure mode than outright
    # absence (a buggy "key in dict" check without a value check would miss this).
    lines, seconds, raw = build_record(
        base_spec, p_kwargs={"engine": "X", "blank": ("host_role",)})
    got = fp.analyze(lines)
    case("empty P key (host_role): rc 2", got["rc"], 2)
    case("empty P key (host_role): reasons non-empty", len(got["reasons"]) > 0, True)

    # The DYNAMIC key proc_cmdline_<launcher>: missing for the launcher the
    # CURRENT engine (X -> surf) actually names, not a fixed literal key.
    lines, seconds, raw = build_record(
        base_spec, p_kwargs={"engine": "X", "omit": ("proc_cmdline_surf",)})
    got = fp.analyze(lines)
    case("missing dynamic P key (proc_cmdline_surf): rc 2", got["rc"], 2)
    case("missing dynamic P key (proc_cmdline_surf): reasons non-empty",
         len(got["reasons"]) > 0, True)

    # kiosk_nrestarts_end != kiosk_nrestarts_start: a restart happened mid-run.
    lines, seconds, raw = build_record(
        base_spec, p_kwargs={"engine": "X", "nrestarts_end": "4"})
    got = fp.analyze(lines)
    case("nrestarts mismatch: rc 2", got["rc"], 2)
    case("nrestarts mismatch: reasons non-empty", len(got["reasons"]) > 0, True)

    # boot_id_end != boot_id: a reboot happened mid-run.
    lines, seconds, raw = build_record(
        base_spec, p_kwargs={"engine": "X", "boot_id_end": "a-different-boot"})
    got = fp.analyze(lines)
    case("boot_id mismatch: rc 2", got["rc"], 2)
    case("boot_id mismatch: reasons non-empty", len(got["reasons"]) > 0, True)

    # browser_procs names neither the X server (comm "X") nor wpe-kiosk:
    # engine cannot be derived.
    lines, seconds, raw = build_record(base_spec, p_kwargs={"engine": "neither"})
    got = fp.analyze(lines)
    case("engine ambiguous (neither): rc 2", got["rc"], 2)
    case("engine ambiguous (neither): reasons non-empty", len(got["reasons"]) > 0, True)

    # browser_procs names BOTH the X server and wpe-kiosk: engine cannot be
    # derived either -- a different failure mode than "neither" (a buggy
    # "elif" chain that just checks X first would read this as X, not
    # ambiguous).
    lines, seconds, raw = build_record(base_spec, p_kwargs={"engine": "both"})
    got = fp.analyze(lines)
    case("engine ambiguous (both): rc 2", got["rc"], 2)
    case("engine ambiguous (both): reasons non-empty", len(got["reasons"]) > 0, True)


# ------------------------------------------------------------------- M lines

def m_line_cases():
    # kiosk-framepace.py's own CLI appends one `M key=value` line per metric
    # to a complete record (its docstring: "a record with the metrics
    # appended reads the same"). Build those M lines exactly as that CLI
    # does, append them to an already-valid record, and re-analyze: the
    # result must come back identical -- M lines are parsed and skipped.
    base_spec = [("motion", 120, DT)]
    lines, seconds, raw = build_record(base_spec)
    result = fp.analyze(lines)
    m_lines = [f"M {k}={v:.3f}" if isinstance(v, float) else f"M {k}={v}"
               for k, v in result.items() if k not in ("rc", "reasons")]
    case("M lines are skipped on re-analysis: identical result",
         fp.analyze(lines + m_lines), result)

    # Any OTHER unrecognised line is not silently skipped like M -- rc 2.
    got = fp.analyze(lines + ["Q foo=bar"])
    case("an unrecognised line: rc 2", got["rc"], 2)
    case("an unrecognised line: reasons non-empty", len(got["reasons"]) > 0, True)


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
    global fp
    fp = load("kiosk-framepace")
    rc0_cases()
    rc2_cases()
    p_block_cases()
    m_line_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cli_cases(tmp)
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
