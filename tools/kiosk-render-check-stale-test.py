#!/usr/bin/env python3
"""Self-test for the STALE verdict in kiosk-render-check.sh. Run by hand --
not wired into just guards or ci-guards.sh, like the tool it tests.

    kiosk-render-check-stale-test.py    -- every case, both directions

THE CONTRACT THIS PINS, rewritten so kiosk-render-check-stale.py IS
docs/issue_investigation/wpe_evaluation/analyze_burst_v3.py's classifier --
the instrument that actually found and proved the fault live -- not a
separate set of rules:

  stale_verdict(bursts) -> {"rc": 0|2|3, "persistent_tiles": int,
                             "persistent_tiles_excl_late_change": int}

  bursts: a list of bursts, each burst a list of capture dicts, in
  CHRONOLOGICAL order within the burst: {"fb_before": int, "fb_after": int,
  "ppm": bytes}. "ppm" is the raw bytes of a binary PPM (P6) capture.

  v3's rules, verbatim:
  - Within a burst, only STABLE captures count (fb_before == fb_after).
    Group them by fb id, in the order each fb id is first seen.
  - Fixed 40x40-pixel tiles.
  - A tile is TESTABLE in a burst only when >=2 distinct fb ids are
    present AND every fb group's own captures are byte-IDENTICAL on that
    tile (exact equality, not a tolerance) -- otherwise the tile is
    skipped, not scored either way.
  - A testable tile DISAGREES when the first fb group's value differs
    from any other group's value by MAD > 1 (mean absolute difference
    over the R/G/B bytes).
  - LATE-CHANGE ARTIFACT: across the burst's full chronological sequence
    of stable captures (every fb group combined, not pairwise), the
    tile's content changes at MOST once, and that one change point
    exactly separates "all of one single fb id" from "all of one single
    OTHER fb id".

  PERSISTENCE AND rc ARE ON THE RAW DISAGREEMENT, LATE-CHANGE EXCLUSION
  NOT APPLIED -- amended against real data (Runs 52-62, scratchpad
  run): with the exclusion in the persistence rule, the faulty baseline
  B0 (Run 52) read 0 persistent tiles, a miss on the real fault, exactly
  the gap that made the old STALE detector miss it live. Without the
  exclusion, every faulty run was flagged (B0 47, B2 47, T3 50, T5 36)
  and every fixed run read 0 in every burst -- complete separation.

  - PERSISTENT: a tile disagreeing (RAW, no late-change exclusion) in
    >=2 CONSECUTIVE bursts.
  - rc=3 (STALE) iff >=1 persistent tile (raw).
  - rc=2 (could not tell) iff the data cannot support a verdict in ANY
    burst: fewer than 2 distinct fb ids among that burst's stable
    captures, or zero testable tiles in that burst (Run 77's vacuous
    case). This takes priority over rc=3/rc=0 regardless of what any
    other burst shows.
  - rc=0 iff every burst is testable (passes neither rc=2 condition) and
    no tile persists (raw).
  - The late-change-excluded persistence count is STILL COMPUTED
    (persistent_tiles_excl_late_change) and printed, informational
    only -- it never feeds rc.

  CLI: `kiosk-render-check-stale.py <manifest>`, where <manifest> is a
  text file, one line per capture, in chronological order, grouped into
  bursts by BLANK LINES:

      fb_before=<id> fb_after=<id> ppm=<path-to-ppm-file>

  It prints exactly two evidence lines to stdout, `persistent
  tiles=<n>` (n is persistent_tiles, the one that drives rc) and
  `persistent tiles (late-change excluded)=<m>` (informational), and
  exits with persistent_tiles' rc.

This CLI/manifest shape -- the blank-line burst separator, and the two
`persistent tiles` evidence lines -- is this test's own design: the
spec fixes the pure-logic rule and the exit codes, not the on-disk
format between this helper and kiosk-render-check.sh. Flag before
matching it if a different shape is wanted.

Fixtures use an 80x80 frame (2x2 real 40x40 tiles): the tile under test is
always (0, 0); a uniform, constant background fills everywhere else in
every capture, so no other tile can register. The two primary verdict
shapes (STALE, pass) use the real series shape run-feature-trial.sh
produces -- 6 bursts of 15 frames -- since that is what produced the
decisive Runs 52-62; the narrower rc=2 and late-change-exclusion cases
use the smallest burst count that isolates the one condition under test.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

TILE = 40
W, H = 80, 80
BG = (100, 100, 100)
A = (0, 0, 0)
B = (255, 255, 255)

PASS, FAIL = [], []


def case(name, got, want):
    (PASS if got == want else FAIL).append(name)
    if got != want:
        print(f"FAIL  {name}\n        want {want!r}\n        got  {got!r}")


def load(name):
    """kiosk-render-check-stale.py, imported by path: the filename is not a
    module name."""
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stale = load("kiosk-render-check-stale")


# --------------------------------------------------------------- fixtures

def ppm(tile_rgb=None, base=BG):
    buf = bytearray(bytes(base) * (W * H))
    if tile_rgb is not None:
        for y in range(TILE):
            off = (y * W) * 3
            buf[off:off + TILE * 3] = bytes(tile_rgb) * TILE
    header = f"P6\n{W} {H}\n255\n".encode()
    return header + bytes(buf)


def whole_frame_ppm(base):
    """No tile override: the ENTIRE frame is one colour, used to make an fb
    group inconsistent everywhere (fixture 4) rather than on tile (0, 0)
    alone -- the background elsewhere is otherwise constant across every
    capture, which would leave every tile but (0, 0) testable."""
    header = f"P6\n{W} {H}\n255\n".encode()
    return header + bytes(base) * (W * H)


def cap(fb, tile_rgb=None):
    """A stable capture (fb_before == fb_after == fb)."""
    return {"fb_before": fb, "fb_after": fb, "ppm": ppm(tile_rgb)}


def interleaved_burst(n=15):
    """n captures alternating fb 1 (value A) / fb 2 (value B) at tile
    (0, 0) -- not a clean split in either fb id or content, so the
    late-change exclusion cannot apply."""
    return [cap(1 if i % 2 == 0 else 2, A if i % 2 == 0 else B) for i in range(n)]


def clean_split_burst(n=15):
    """n captures: all fb 1 (value A) then all fb 2 (value B) -- a clean
    split in BOTH fb id and content, exactly once -- the late-change
    exclusion applies."""
    half = n // 2
    return [cap(1 if i < half else 2, A if i < half else B) for i in range(n)]


def matching_burst(n=15):
    """n captures, fb 1 and fb 2 alternating, identical content -- no
    disagreement at all."""
    return [cap(1 if i % 2 == 0 else 2, A) for i in range(n)]


def verdict_cases():
    # 1. STALE: the same interleaved (non-excludable) disagreement in
    # every one of 6 bursts of 15 frames -- run-feature-trial.sh's real
    # series shape.
    case("persistent disagreement across every burst -> STALE",
         stale.stale_verdict([interleaved_burst(15) for _ in range(6)]),
         {"rc": 3, "persistent_tiles": 1, "persistent_tiles_excl_late_change": 1})

    # 2a. Pass: no disagreement anywhere, same 6x15 shape.
    case("no disagreement anywhere -> pass",
         stale.stale_verdict([matching_burst(15) for _ in range(6)]),
         {"rc": 0, "persistent_tiles": 0, "persistent_tiles_excl_late_change": 0})

    # 2b. Pass: disagreement in exactly one burst, isolated -- never 2
    # consecutive bursts, so never persistent. Sharper than 2a: proves the
    # >=2-CONSECUTIVE threshold, not just "equal is fine".
    case("disagreement in a single, non-consecutive burst -> pass, not persistent",
         stale.stale_verdict([
             matching_burst(15), matching_burst(15), interleaved_burst(15),
             matching_burst(15), matching_burst(15), matching_burst(15),
         ]),
         {"rc": 0, "persistent_tiles": 0, "persistent_tiles_excl_late_change": 0})

    # 3. Could not tell: burst 1 has only fb=1 (fewer than 2 distinct fb
    # ids among its stable captures) -- rc=2 regardless of burst 2's own
    # persistent-looking disagreement, proving rc=2 takes priority.
    case("a burst without both fb groups having a stable capture -> could not tell",
         stale.stale_verdict([
             [cap(1, A) for _ in range(5)],
             interleaved_burst(15),
         ]),
         {"rc": 2, "persistent_tiles": 0, "persistent_tiles_excl_late_change": 0})

    # 4. Could not tell: 2 distinct fb ids are present, but fb=1's own
    # captures disagree with EACH OTHER over the WHOLE frame (not just one
    # tile), so no tile anywhere has both groups self-consistent --
    # zero testable tiles (Run 77's vacuous case).
    case("zero testable tiles in a burst -> could not tell, never a pass",
         stale.stale_verdict([[
             {"fb_before": 1, "fb_after": 1, "ppm": whole_frame_ppm(A)},
             {"fb_before": 2, "fb_after": 2, "ppm": whole_frame_ppm((128, 128, 128))},
             {"fb_before": 1, "fb_after": 1, "ppm": whole_frame_ppm(B)},
             {"fb_before": 2, "fb_after": 2, "ppm": whole_frame_ppm((128, 128, 128))},
         ]]),
         {"rc": 2, "persistent_tiles": 0, "persistent_tiles_excl_late_change": 0})

    # 5. AMENDED (real-data finding): the SAME clean-split content change,
    # repeated in 2 consecutive bursts, now DOES count as persistent and
    # IS rc=3 -- persistence is on the raw disagreement, not the late-
    # change-excluded one. The excluded count is still 0 (both bursts'
    # late-change exclusion still applies individually), proving the two
    # counts can genuinely differ.
    case("a tile changing once mid-burst, repeated in 2 consecutive bursts -> STALE (raw)",
         stale.stale_verdict([clean_split_burst(15), clean_split_burst(15)]),
         {"rc": 3, "persistent_tiles": 1, "persistent_tiles_excl_late_change": 0})

    # 6. B0-shaped (Run 52, the real faulty baseline the exclusion used to
    # miss): no disagreement in burst 1, then the SAME late-change-shaped
    # disagreement in bursts 2 and 3, overlapping -> raw-persistent across
    # bursts 2-3 -> STALE, even though every instance individually looks
    # like a legitimate one-time repaint.
    case("B0-shaped: late-change-looking disagreement overlapping in bursts 2-3 -> STALE",
         stale.stale_verdict([matching_burst(15), clean_split_burst(15), clean_split_burst(15)]),
         {"rc": 3, "persistent_tiles": 1, "persistent_tiles_excl_late_change": 0})


# ------------------------------------------------------------------- CLI
#
# The boundary kiosk-render-check.sh will actually cross: a manifest file on
# disk, this helper's own process exit code, and the one stdout line it maps
# into its rc. Tested end to end via subprocess, not by calling into main().

def write_manifest(tmp, bursts):
    lines = []
    i = 0
    for burst in bursts:
        for c in burst:
            p = tmp / f"frame{i}.ppm"
            p.write_bytes(c["ppm"])
            lines.append(f"fb_before={c['fb_before']} fb_after={c['fb_after']} ppm={p}")
            i += 1
        lines.append("")  # blank line: burst separator
    manifest = tmp / "manifest.txt"
    manifest.write_text("\n".join(lines) + "\n")
    return manifest


def run_cli(manifest):
    return subprocess.run(
        [sys.executable, str(TOOLS / "kiosk-render-check-stale.py"), str(manifest)],
        capture_output=True, text=True)


def cli_cases(tmp_path):
    from pathlib import Path as P
    stale_dir = P(tmp_path) / "stale-cli"
    pass_dir = P(tmp_path) / "pass-cli"
    cant_tell_dir = P(tmp_path) / "cant-tell-cli"
    b0_dir = P(tmp_path) / "b0-cli"
    for d in (stale_dir, pass_dir, cant_tell_dir, b0_dir):
        d.mkdir(parents=True)

    manifest = write_manifest(stale_dir, [interleaved_burst(15) for _ in range(6)])
    got = run_cli(manifest)
    case("CLI: STALE exits 3", got.returncode, 3)
    case("CLI: STALE evidence line", "persistent tiles=1" in got.stdout.splitlines(), True)
    case("CLI: STALE excl-late-change evidence line",
         "persistent tiles (late-change excluded)=1" in got.stdout.splitlines(), True)

    manifest = write_manifest(pass_dir, [matching_burst(15) for _ in range(6)])
    got = run_cli(manifest)
    case("CLI: pass exits 0", got.returncode, 0)
    case("CLI: pass evidence line", "persistent tiles=0" in got.stdout.splitlines(), True)

    manifest = write_manifest(
        cant_tell_dir, [[cap(1, A) for _ in range(5)], interleaved_burst(15)])
    got = run_cli(manifest)
    case("CLI: could-not-tell exits 2", got.returncode, 2)
    case("CLI: could-not-tell evidence line",
         "persistent tiles=0" in got.stdout.splitlines(), True)

    # The two evidence lines must be able to genuinely differ: raw
    # persistence is judged (drives rc), the late-change-excluded count is
    # informational only.
    manifest = write_manifest(b0_dir, [clean_split_burst(15), clean_split_burst(15)])
    got = run_cli(manifest)
    case("CLI: B0-shaped exits 3 (raw persistence, not the excluded count)",
         got.returncode, 3)
    case("CLI: B0-shaped persistent tiles=1 (raw)",
         "persistent tiles=1" in got.stdout.splitlines(), True)
    case("CLI: B0-shaped excl-late-change=0 (differs from the raw count)",
         "persistent tiles (late-change excluded)=0" in got.stdout.splitlines(), True)


def main() -> int:
    import tempfile
    verdict_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cli_cases(tmp)
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
