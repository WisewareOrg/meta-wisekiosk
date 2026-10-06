#!/usr/bin/env python3
"""Frame-pacing metrics from a kiosk-framepace record, or why none can be given.

    kiosk-framepace.py <record>

The record is the driver's provenance block (`P key=value` lines) followed by the
device tool's output, whose format is documented in the header of
meta-wisekiosk/recipes-graphics/kiosk-drmgrab/files/kiosk-framepace.c.

A presented frame is a sample whose hash differs from the previous sample's;
intervals run between consecutive presented frames. An interval of 1.5 s or more
is a hold (the app holds 2 s in each 8 s marquee cycle): its excess over 2.0 s,
when above 0.25 s, is one stall of that size. Shorter intervals are motion; a
motion interval above 0.25 s is one stall of its own size.

Metrics, over motion intervals: presented_fps (motion intervals / motion seconds),
pct_under_50 (% of motion intervals under 50 ms), stalls, stall_rate (stalls per
minute of the declared window) and max_stall_ms; plus engine, X or WPE.

Exit 0 with one `M key=value` line per metric. `M` lines in the record are skipped,
so a record with the metrics appended reads the same. Exit 2, printing each reason as
"could not tell: <reason>", when the record is incomplete or malformed, the mode is
not 1280x720, fewer than 90 % of the samples the pacing should give are present,
motion covers under half the window, the provenance block is missing a field, the
kiosk restarted or the board rebooted during the run, or the engine is ambiguous.
"""
import re
import sys
from itertools import pairwise

HOLD_S = 1.5
HOLD_NOMINAL_S = 2.0
STALL_S = 0.25
FAST_S = 0.050
MIN_SAMPLE_FRACTION = 0.9
MIN_MOTION_FRACTION = 0.5
PACING_HZ = {"timer100": 100}

HEADER_KEYS = ("tool", "mode", "pacing", "regions", "start", "seconds", "cpu_ms",
               "samples", "missed", "end")
P_KEYS = ("tools_commit", "host_role", "buildinfo_wisekiosk", "slot", "kiosk_conf_sha256",
          "kiosk_conf", "browser_procs", "crtc_state", "kiosk_nrestarts_start",
          "kiosk_nrestarts_end", "boot_id", "boot_id_end", "uptime_s", "screenshot")
LAUNCHER = {"X": "surf", "WPE": "wpe-kiosk"}
SAMPLE = re.compile(r"(\d+) (\d+) ([0-9a-f]{16}) (\d+|-)")
MODE = re.compile(r"(\d+)x(\d+)@(\d+)")


def parse(lines):
    """(header, provenance, samples [(t_ns, hash)], reasons) from the record's lines."""
    header, prov, samples, reasons = {}, {}, [], []
    for n, line in enumerate(lines, 1):
        kind, _, rest = line.rstrip("\n").partition(" ")
        if (kind == "" and rest == "") or kind == "M":
            continue
        if kind == "S":
            m = SAMPLE.fullmatch(rest)
            if not m:
                reasons.append(f"line {n}: malformed sample")
                continue
            samples.append((int(m[1]), m[3]))
        elif kind == "H" and rest.startswith("samples="):
            for token in rest.split():
                key, _, value = token.partition("=")
                header[key] = value
        elif kind == "H":
            key, _, value = rest.partition("=")
            header[key] = value
        elif kind == "P":
            key, _, value = rest.partition("=")
            prov[key] = value
        else:
            reasons.append(f"line {n}: unrecognised line")
    return header, prov, samples, reasons


def engine_of(prov, reasons):
    comms = {p.partition(":")[2] for p in prov.get("browser_procs", "").split(",")}
    engines = [e for e, comm in (("X", "X"), ("WPE", "wpe-kiosk")) if comm in comms]
    if len(engines) != 1:
        reasons.append("browser_procs names " + ("both X and wpe-kiosk" if engines
                                                 else "neither X nor wpe-kiosk"))
        return None
    return engines[0]


def check_provenance(prov, reasons):
    engine = engine_of(prov, reasons)
    keys = list(P_KEYS)
    if engine:
        keys += [f"proc_cmdline_{LAUNCHER[engine]}", f"proc_environ_{LAUNCHER[engine]}"]
    for key in keys:
        if not prov.get(key):
            reasons.append(f"provenance field {key} is missing or empty")
    if prov.get("kiosk_nrestarts_end") != prov.get("kiosk_nrestarts_start"):
        reasons.append("the kiosk restarted during the run")
    if prov.get("boot_id_end") != prov.get("boot_id"):
        reasons.append("the board rebooted during the run")
    return engine


def intervals_s(samples):
    frames = [t for (_, ph), (t, h) in pairwise(samples) if h != ph]
    return [(b - a) / 1e9 for a, b in pairwise(frames)]


def analyze(lines):
    header, prov, samples, reasons = parse(lines)
    engine = check_provenance(prov, reasons)
    missing = [k for k in HEADER_KEYS if k not in header]
    if "end" not in header:
        reasons.append("no end line: the run did not complete")
    elif missing:
        reasons.append("header fields missing: " + ", ".join(missing))
    mode = MODE.fullmatch(header.get("mode", ""))
    if "mode" in header and not (mode and (mode[1], mode[2]) == ("1280", "720")):
        reasons.append(f"mode {header['mode']} is not 1280x720")
    pacing = header.get("pacing", "").split(" ")[0]
    seconds = header.get("seconds", "")
    if not seconds.isdigit() or int(seconds) == 0:
        if "seconds" in header:
            reasons.append(f"seconds={seconds} is not a positive integer")
        return {"rc": 2, "reasons": reasons}
    seconds = int(seconds)
    if pacing == "vblank" and mode:
        hz = int(mode[3])
    elif pacing in PACING_HZ:
        hz = PACING_HZ[pacing]
    else:
        reasons.append(f"pacing {header.get('pacing', '')!r} gives no expected sample rate")
        return {"rc": 2, "reasons": reasons}
    if len(samples) < MIN_SAMPLE_FRACTION * seconds * hz:
        reasons.append(f"{len(samples)} samples, under 90 % of the {seconds * hz} expected")

    deltas = intervals_s(samples)
    motion = [d for d in deltas if d < HOLD_S]
    stall_ms = [d * 1000 for d in motion if d > STALL_S]
    stall_ms += [(d - HOLD_NOMINAL_S) * 1000 for d in deltas
                 if d >= HOLD_S and d - HOLD_NOMINAL_S > STALL_S]
    motion_s = sum(motion)
    if motion_s < MIN_MOTION_FRACTION * seconds:
        reasons.append(f"motion covers {motion_s:.1f} s of {seconds} s: the marquee was not moving")
    if reasons:
        return {"rc": 2, "reasons": reasons}
    return {
        "rc": 0,
        "reasons": [],
        "engine": engine,
        "presented_fps": len(motion) / motion_s,
        "pct_under_50": 100.0 * sum(1 for d in motion if d < FAST_S) / len(motion),
        "stalls": len(stall_ms),
        "stall_rate": len(stall_ms) / (seconds / 60.0),
        "max_stall_ms": max(stall_ms, default=0.0),
    }


def main(argv):
    if len(argv) != 2:
        print("usage: kiosk-framepace.py <record>", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        result = analyze(f.read().splitlines())
    for reason in result["reasons"]:
        print(f"could not tell: {reason}")
    for key, value in result.items():
        if key not in ("rc", "reasons"):
            print(f"M {key}={value:.3f}" if isinstance(value, float) else f"M {key}={value}")
    return result["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
