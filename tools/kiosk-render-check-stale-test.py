#!/usr/bin/env python3
"""Self-test for the STALE verdict in kiosk-render-check.sh. Run by hand --
not wired into just guards or ci-guards.sh, like the tool it tests.

    kiosk-render-check-stale-test.py    -- every case, both directions

THE CONTRACT THIS PINS, since kiosk-render-check-stale.py does not exist yet
and this test is what fixes its shape:

  stale_verdict(captures) -> {"rc": 0|2|3, "stale_tiles": int}

  captures: a list of dicts, one per kiosk-drmgrab capture, in CHRONOLOGICAL
  order: {"fb_before": int, "fb_after": int, "ppm": bytes}. "ppm" is the raw
  bytes of a binary PPM (P6) capture of the checked region.

  Rule: use stable captures only (fb_before == fb_after). Group them by fb
  id. An fb with >=1 stable capture is COMPARABLE; self-consistency (MAD
  <= 1 over the R/G/B bytes, against that fb's first stable capture) is
  checked only for an fb with >=2 -- a singleton has nothing to self-check
  and counts as consistent. Grid: fixed 40x40-PIXEL tiles over the frame,
  not 40 divisions per axis -- a 1280x720 region is 32x18 tiles. A
  dimension not divisible by 40 leaves a partial edge tile, whose MAD is
  computed over its own actual pixels, not a full 40x40. A tile DISAGREES
  when (a) both fbs are self-consistent on it, and (b) between the two fbs
  it differs (MAD > 1) -- unless the fb-id sequence among the stable
  captures is a single chronological split (every capture of one id before
  every capture of the other), which is a legitimate one-time repaint, not
  staleness. rc=3 iff >=1 tile disagrees. rc=2 iff NO fb reaches >=2 stable
  captures -- covers zero stable captures in total (every capture unstable)
  and two fbs with exactly 1 stable capture each: nothing is left to
  self-check, so a series that cannot be tested must not pass. One fb id
  seen with >=2 stable captures: no alternation is possible, rc=0. Any
  capture's PPM failing to parse (truncated): rc=2, never a pass.

  CLI: `kiosk-render-check-stale.py <manifest>`, where <manifest> is a text
  file, one line per capture in chronological order:

      fb_before=<id> fb_after=<id> ppm=<path-to-ppm-file>

  It prints exactly one evidence line to stdout, `stale tiles=<n>` (n is
  stale_tiles from stale_verdict), and exits with that result's rc.

This CLI/manifest shape is this test's own design -- #185's spec fixes the
pure-logic rule and the exit codes, not the on-disk format between this
helper and kiosk-render-check.sh. Flag before matching it if a different
shape is wanted.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

TILE = 40              # pixels, fixed -- not a divisions-per-axis count
W, H = 80, 80          # 2x2 whole tiles at the fixed 40px size
BG = (100, 100, 100)
C0 = (0, 0, 0)
C128 = (128, 128, 128)
C255 = (255, 255, 255)

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
#
# A synthetic frame per capture, a uniform background with one tile
# overridden where a case needs it to differ. Most cases use an 80x80 frame
# (an exact 2x2 grid of real 40x40 tiles) and tile (0, 0); the partial-edge
# case below uses a frame whose dimensions are not multiples of 40. Every
# fixture is checked against a scratch reference oracle before being
# trusted here -- not shipped, not re-run by this file.

def ppm(w=W, h=H, ti=0, tj=0, tile_rgb=None, base=BG):
    buf = bytearray(bytes(base) * (w * h))
    if tile_rgb is not None:
        x0, y0 = ti * TILE, tj * TILE
        x1, y1 = min(x0 + TILE, w), min(y0 + TILE, h)
        for y in range(y0, y1):
            off = (y * w + x0) * 3
            buf[off:off + (x1 - x0) * 3] = bytes(tile_rgb) * (x1 - x0)
    header = f"P6\n{w} {h}\n255\n".encode()
    return header + bytes(buf)


def cap(fb_before, fb_after, tile_rgb=None, w=W, h=H, ti=0, tj=0):
    return {"fb_before": fb_before, "fb_after": fb_after,
            "ppm": ppm(w, h, ti, tj, tile_rgb)}


def verdict_cases():
    # A static tile differing between fb A and fb B, fb ids interleaved so
    # the late-change exclusion cannot apply -> STALE.
    case("interleaved tile disagreement -> STALE",
         stale.stale_verdict(
             [cap(1, 1, C0), cap(2, 2, C255), cap(1, 1, C0), cap(2, 2, C255)]),
         {"rc": 3, "stale_tiles": 1})

    # Both fbs' content fully identical -> pass.
    case("both fbs identical -> pass",
         stale.stale_verdict([cap(1, 1), cap(1, 1), cap(2, 2), cap(2, 2)]),
         {"rc": 0, "stale_tiles": 0})

    # Fb ids form a single chronological split and the tile changes exactly
    # at that split -> a legitimate one-time repaint, excluded.
    case("late-change, clean split -> pass",
         stale.stale_verdict(
             [cap(1, 1, C0), cap(1, 1, C0), cap(2, 2, C255), cap(2, 2, C255)]),
         {"rc": 0, "stale_tiles": 0})

    # Only one fb id among the stable captures: no alternation is possible,
    # regardless of how the tile's own content varies.
    case("only one fb id -> pass",
         stale.stale_verdict([cap(1, 1, C0), cap(1, 1, C128), cap(1, 1, C255)]),
         {"rc": 0, "stale_tiles": 0})

    # AMENDED (was "insufficient stable captures -> could not tell", fixed
    # rc=2): under the comparable-singleton rule, fb 1's single stable
    # capture is comparable against fb 2's self-consistent pair. But the
    # fb-id sequence here ([1, 2, 2]) is a clean chronological split, so the
    # tile's difference is the late-change exclusion, not a disagreement --
    # a pass, not could-not-tell. This fixture no longer tests insufficient
    # data (new cases below cover that); it now pins that a comparable
    # singleton does not bypass the late-change exclusion.
    case("singleton fb + clean split -> pass, not could-not-tell",
         stale.stale_verdict([cap(1, 1, C0), cap(2, 2, C255), cap(2, 2, C255)]),
         {"rc": 0, "stale_tiles": 0})

    # fb A has 1 stable capture that differs on a static tile; fb B has 3
    # identical stable captures. Order is B, A, B, B -- not a clean split --
    # so A's singleton capture is still comparable and the disagreement is
    # not excluded as a late change.
    case("singleton fb disagrees with a self-consistent fb -> STALE",
         stale.stale_verdict([
             cap(2, 2, C255), cap(1, 1, C0), cap(2, 2, C255), cap(2, 2, C255),
         ]),
         {"rc": 3, "stale_tiles": 1})

    # Two fbs, each with exactly 1 stable capture: neither reaches the >=2
    # self-consistency threshold, so nothing here can ever be verified.
    case("two singleton fbs -> could not tell",
         stale.stale_verdict([cap(1, 1, C0), cap(2, 2, C255)]),
         {"rc": 2, "stale_tiles": 0})

    # Every capture is unstable (fb_before != fb_after): zero stable
    # captures in total. A series that cannot be tested must not pass, so
    # this is could-not-tell, never the "nothing to compare" pass that a
    # single-fb-id read might otherwise suggest.
    case("every capture unstable -> could not tell, never a pass",
         stale.stale_verdict([cap(1, 2, C0), cap(2, 1, C255)]),
         {"rc": 2, "stale_tiles": 0})

    # The boundary this contrasts with: exactly 2 stable captures (the
    # minimum that counts), one fb id, differing content -> still a pass.
    case("single fb id at the 2-capture boundary -> pass",
         stale.stale_verdict([cap(1, 1, C0), cap(1, 1, C255)]),
         {"rc": 0, "stale_tiles": 0})

    # A truncated capture forces could-not-tell, never a pass -- even though
    # the other three captures alone would read as a clean late-change.
    truncated = ppm(tile_rgb=C0)[:-500]
    case("truncated capture -> could not tell, never a pass",
         stale.stale_verdict([
             cap(1, 1, C0), cap(1, 1, C0),
             {"fb_before": 2, "fb_after": 2, "ppm": truncated},
             cap(2, 2, C255),
         ]),
         {"rc": 2, "stale_tiles": 0})

    # An unstable capture (fb_before != fb_after) sits between two genuinely
    # disagreeing, interleaved fbs, carrying a THIRD tile value. If it were
    # not ignored and were folded into fb 2's group (its fb_after), fb 2's
    # own captures would read [255, 128, 255] -- not internally stable
    # (MAD(255, 128) = 127 > 1) -- which would suppress the real
    # disagreement and wrongly return a pass. Ignoring it correctly leaves
    # fb 2's stable captures as [255, 255], still disagreeing with fb 1.
    case("unstable capture ignored, disagreement still found -> STALE",
         stale.stale_verdict([
             cap(1, 1, C0), cap(2, 2, C255),
             {"fb_before": 1, "fb_after": 2, "ppm": ppm(tile_rgb=C128)},
             cap(1, 1, C0), cap(2, 2, C255),
         ]),
         {"rc": 3, "stale_tiles": 1})

    # A 100x60 frame is not a multiple of the fixed 40px tile: tiles_x =
    # ceil(100/40) = 3 (0-39, 40-79, 80-99 -- 20px wide), tiles_y =
    # ceil(60/40) = 2 (0-39, 40-59 -- 20px tall). Tile (2, 1), the
    # bottom-right corner, is doubly partial: 20x20 actual pixels. The
    # disagreement is painted ONLY there, interleaved so no exclusion
    # applies -- proving an edge tile is included and its MAD is computed
    # over its real (smaller) pixel count, not a full 40x40.
    case("partial edge tile (20x20 px) disagrees -> STALE",
         stale.stale_verdict([
             cap(1, 1, C0, w=100, h=60, ti=2, tj=1),
             cap(2, 2, C255, w=100, h=60, ti=2, tj=1),
             cap(1, 1, C0, w=100, h=60, ti=2, tj=1),
             cap(2, 2, C255, w=100, h=60, ti=2, tj=1),
         ]),
         {"rc": 3, "stale_tiles": 1})


# ------------------------------------------------------------------- CLI
#
# The boundary kiosk-render-check.sh will actually cross: a manifest file on
# disk, this helper's own process exit code, and the one stdout line it maps
# into its rc. Tested end to end via subprocess, not by calling into main().

def write_manifest(tmp, captures):
    lines = []
    for i, c in enumerate(captures):
        p = tmp / f"frame{i}.ppm"
        p.write_bytes(c["ppm"])
        lines.append(f"fb_before={c['fb_before']} fb_after={c['fb_after']} ppm={p}")
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
    identical_dir = P(tmp_path) / "identical-cli"
    short_dir = P(tmp_path) / "short-cli"
    for d in (stale_dir, identical_dir, short_dir):
        d.mkdir(parents=True)

    manifest = write_manifest(
        stale_dir,
        [cap(1, 1, C0), cap(2, 2, C255), cap(1, 1, C0), cap(2, 2, C255)])
    got = run_cli(manifest)
    case("CLI: STALE exits 3", got.returncode, 3)
    case("CLI: STALE evidence line", "stale tiles=1" in got.stdout.splitlines(), True)

    manifest = write_manifest(
        identical_dir, [cap(1, 1), cap(1, 1), cap(2, 2), cap(2, 2)])
    got = run_cli(manifest)
    case("CLI: pass exits 0", got.returncode, 0)
    case("CLI: pass evidence line", "stale tiles=0" in got.stdout.splitlines(), True)

    # AMENDED: this used to be [cap(1,1,C0), cap(2,2,C255), cap(2,2,C255)]
    # ("insufficient" under the old either-group-<2 rule). Under the
    # comparable-singleton rule that fixture is a clean-split pass, not
    # could-not-tell -- see the amended verdict_cases() comment. Two
    # singleton fbs is the fixture that still forces rc=2 here.
    manifest = write_manifest(
        short_dir, [cap(1, 1, C0), cap(2, 2, C255)])
    got = run_cli(manifest)
    case("CLI: could-not-tell exits 2", got.returncode, 2)
    case("CLI: could-not-tell evidence line",
         "stale tiles=0" in got.stdout.splitlines(), True)


def main() -> int:
    import tempfile
    verdict_cases()
    with tempfile.TemporaryDirectory() as tmp:
        cli_cases(tmp)
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
