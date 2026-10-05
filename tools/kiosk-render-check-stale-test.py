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

  Rule: use stable captures only (fb_before == fb_after). Group them by fb id.
  Grid: a fixed 40x40 tiles over the frame. A tile DISAGREES when (a) within
  each fb's own stable captures the tile is identical (MAD <= 1 over the
  R/G/B bytes), and (b) between the two fbs it differs (MAD > 1) -- unless
  the fb-id sequence among the stable captures is a single chronological
  split (every capture of one id before every capture of the other), which is
  a legitimate one-time repaint, not staleness. rc=3 iff >=1 tile disagrees.
  One fb id seen: no alternation is possible, rc=0. Two fb ids but either has
  fewer than 2 stable captures, or any capture's PPM is truncated: rc=2,
  never a pass.

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

W, H = 80, 80          # divisible by the fixed 40x40 grid: tile = 2x2 px
TILE_PX = W // 40
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
# One 80x80 synthetic frame per capture, a uniform background with tile
# (0, 0) overridden where a case needs it to differ. Every fixture is
# checked against a scratch reference oracle before being trusted here --
# not shipped, not re-run by this file.

def ppm(tile_rgb=None, base=BG):
    buf = bytearray(bytes(base) * (W * H))
    if tile_rgb is not None:
        for yy in range(TILE_PX):
            off = (yy * W) * 3
            buf[off:off + TILE_PX * 3] = bytes(tile_rgb) * TILE_PX
    header = f"P6\n{W} {H}\n255\n".encode()
    return header + bytes(buf)


def cap(fb_before, fb_after, tile_rgb=None):
    return {"fb_before": fb_before, "fb_after": fb_after, "ppm": ppm(tile_rgb)}


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

    # Two fb ids, but one has fewer than 2 stable captures.
    case("insufficient stable captures -> could not tell",
         stale.stale_verdict([cap(1, 1, C0), cap(2, 2, C255), cap(2, 2, C255)]),
         {"rc": 2, "stale_tiles": 0})

    # A truncated capture forces could-not-tell, never a pass -- even though
    # the other three captures alone would read as a clean late-change.
    truncated = ppm(C0)[:-500]
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
             {"fb_before": 1, "fb_after": 2, "ppm": ppm(C128)},
             cap(1, 1, C0), cap(2, 2, C255),
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

    manifest = write_manifest(
        short_dir, [cap(1, 1, C0), cap(2, 2, C255), cap(2, 2, C255)])
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
