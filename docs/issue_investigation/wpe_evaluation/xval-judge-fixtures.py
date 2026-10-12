#!/usr/bin/env python3
"""Test-only fixture generator for xval-judge-test.sh. Not shipped, not a copy of
xval-judge.sh's logic -- it only builds PPM/PNG frames; the verdict comes from the real
tool. See xval-judge-test.sh for what each mode is for.

  xval-judge-fixtures.py <mode> <outdir>

Writes A.ppm, A.png, B.ppm, B.png into <outdir>, 1280x720 unless the mode says otherwise.
Geometry (fixed, matches the crops xval-judge-test.sh passes to xval-judge.sh):
  STATIC = x in [50,150), y in [50,150)   -- a 100x100 region, identical across methods
  CLOCK  = x in [600,680), y in [600,640) -- an 80x40 region that moves between A and B
"""
import os
import subprocess
import sys

W, H = 1280, 720
BG = (128, 128, 128)
STATIC = (50, 50, 100, 100)
CLOCK = (600, 600, 80, 40)


def new_frame(w=W, h=H, bg=BG):
    return bytearray(bytes(bg) * (w * h))


def paint_region(buf, w, region, pixel_fn):
    x0, y0, rw, rh = region
    for yy in range(rh):
        y = y0 + yy
        row = bytearray(rw * 3)
        for xx in range(rw):
            r, g, b = pixel_fn(xx, yy)
            i = xx * 3
            row[i], row[i + 1], row[i + 2] = r, g, b
        off = (y * w + x0) * 3
        buf[off:off + rw * 3] = row


def colourful(xx, yy):
    # Plenty of distinct colours and a large |R-B| swing across the region.
    return (xx % 256, yy % 256, (255 - xx) % 256)


def grey_many_levels(xx, yy):
    v = (xx + yy) % 64
    return (v, v, v)


def grey_few_levels(xx, yy):
    v = (xx // 60) * 60 % 256
    return (v, v, v)


def write_ppm(path, w, h, buf):
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        f.write(bytes(buf))


def ppm_to_png(ppm_path, png_path):
    subprocess.run(["magick", ppm_path, png_path], check=True)
    os.remove(ppm_path)


def swap_rb_in_region(buf, w, region):
    out = bytearray(buf)
    x0, y0, rw, rh = region
    for yy in range(rh):
        y = y0 + yy
        off = (y * w + x0) * 3
        for xx in range(rw):
            i = off + xx * 3
            out[i], out[i + 2] = out[i + 2], out[i]
    return out


def shift_tile_in_region(buf, w, h, region, dx=4, dy=4, tile=20):
    # Move one 20x20 tile near the middle of the region by (dx, dy) -- a de-tile-style
    # "block landed in the wrong place" defect, not a colour defect.
    out = bytearray(buf)
    x0, y0, rw, rh = region
    tx, ty = x0 + rw // 2 - tile // 2, y0 + rh // 2 - tile // 2
    src = bytearray(tile * 3)
    for yy in range(tile):
        srow = (ty + yy) * w * 3 + tx * 3
        out[srow:srow + tile * 3] = bytes(tile * 3)  # erase (becomes background-coloured)
    for yy in range(tile):
        srow = (ty + yy) * w * 3 + tx * 3
        drow = (ty + dy + yy) * w * 3 + (tx + dx) * 3
        out[drow:drow + tile * 3] = buf[srow:srow + tile * 3]
    return out


def build_pair(outdir, static_fn, clock_a_rgb, clock_b_rgb, dims=(W, H),
               static_mutation=None, grey=False):
    w, h = dims
    a = new_frame(w, h)
    paint_region(a, w, STATIC, static_fn)
    paint_region(a, w, CLOCK, lambda xx, yy: clock_a_rgb)
    b = new_frame(w, h)
    paint_region(b, w, STATIC, static_fn)
    paint_region(b, w, CLOCK, lambda xx, yy: clock_b_rgb)

    write_ppm(f"{outdir}/A.ppm", w, h, a)
    write_ppm(f"{outdir}/B.ppm", w, h, b)

    a_png = static_mutation(a, w, STATIC) if static_mutation else a
    write_ppm(f"{outdir}/_a_png_src.ppm", w, h, a_png)
    ppm_to_png(f"{outdir}/_a_png_src.ppm", f"{outdir}/A.png")
    write_ppm(f"{outdir}/_b_png_src.ppm", w, h, b)
    ppm_to_png(f"{outdir}/_b_png_src.ppm", f"{outdir}/B.png")


def main():
    mode, outdir = sys.argv[1], sys.argv[2]

    if mode == "pass":
        build_pair(outdir, colourful, (255, 255, 255), (0, 0, 0))
    elif mode == "channel_swap":
        build_pair(outdir, colourful, (255, 255, 255), (0, 0, 0),
                   static_mutation=lambda buf, w, r: swap_rb_in_region(buf, w, r))
    elif mode == "misplaced_tile":
        build_pair(outdir, colourful, (255, 255, 255), (0, 0, 0),
                   static_mutation=lambda buf, w, r: shift_tile_in_region(buf, w, H, r))
    elif mode == "unchanged_clock":
        build_pair(outdir, colourful, (255, 255, 255), (255, 255, 255))
    elif mode == "wrong_dims":
        build_pair(outdir, colourful, (255, 255, 255), (0, 0, 0))
        # Re-write B.png one pixel short -- still readable, just the wrong size.
        b_short = new_frame(W, H - 1)
        paint_region(b_short, W, STATIC, colourful)
        paint_region(b_short, W, CLOCK, lambda xx, yy: (0, 0, 0))
        write_ppm(f"{outdir}/_b_short.ppm", W, H - 1, b_short)
        ppm_to_png(f"{outdir}/_b_short.ppm", f"{outdir}/B.png")
    elif mode == "flat_crop":
        build_pair(outdir, lambda xx, yy: (200, 10, 10), (255, 255, 255), (0, 0, 0))
    elif mode == "grayscale_pass":
        build_pair(outdir, grey_many_levels, (200, 200, 200), (10, 10, 10))
    elif mode == "grayscale_flat":
        build_pair(outdir, grey_few_levels, (200, 200, 200), (10, 10, 10))
    elif mode == "missing_frame":
        build_pair(outdir, colourful, (255, 255, 255), (0, 0, 0))
        os.remove(f"{outdir}/B.png")
    else:
        sys.exit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
