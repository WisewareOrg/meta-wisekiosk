# Does WPE WebKit + cog replace X11 + surf + WebKitGTK on the Pi Zero W without degrading the kiosk?

| | |
|---|---|
| **Issue** | #185 WPE WebKit evaluation |
| **Status** | open |
| **Opened / concluded** | 2026-10-04 / — |

The kiosk renders one fullscreen page through bare Xorg, `surf` and `webkitgtk3` 2.44.3. This
investigation swaps the base image in place to WPE WebKit 2.44.4 under `cog`, on the integration
branch `185-wpe-evaluation`, and judges it against a baseline measured on the X image beforehand.
Any regression in smoothness, module faults or soak stability is a no-go; slower startup alone is
not. If 2.44.4 passes, one attempt is measured at 2.54. No verdict yet.

## Test runs

No run has landed yet. Each run gets a row here and a `### Run N` block below, naming its board
role and the image commit from `/etc/buildinfo` (R1).

| Run | Board (role) | Image commit | Harness / scripts | Result (1 line) |
|---|---|---|---|---|

## Configuration under test

- **Baseline (X):** the image built from `origin/main` plus the `#185 capture` commits, which add
  only `kiosk-drmgrab` (`meta-wisekiosk/recipes-graphics/kiosk-drmgrab/`). Session:
  `meta-wisekiosk/recipes-core/kiosk-session/` (bare Xorg, `surf` at 1280x720).
- **Candidate (WPE):** the `#185 W1` commits on `185-wpe-evaluation`; the image commit is recorded
  per run once built. `meta-webkit` `scarthgap` at `2d29669a3d78e462276044f3f8bde0e4dec33696`
  (`includes/base.yaml`); `wpewebkit` 2.44.4 with `wpebackend-fdo` (the `wpe` block of
  `kiosk-zero-w.yaml`); `cog -P drm` at 1280x720 (`meta-wisekiosk/recipes-core/kiosk-session/`)
  with the `--user-script` patch (`meta-wisekiosk/recipes-browser/cog/`).
  - **wpewebkit PACKAGECONFIG:** `speech-synthesis` off (flite is not carried), `reduce-size` and
    `woff2` on, `jit` off by the recipe on armv6. Every other recipe default stays on —
    `accessibility`, `avif`, `jpegxl`, `mediasource`, `mediastream`, `webaudio`, `gst_gl`,
    `libbacktrace`, `lbse`, `openjpeg`, `service-worker`, `remote-inspector` among them; removing
    any is the levers ticket's, not this investigation's.
  - **Layer shadowing (`bitbake-layers show-overlayed`, W1 parse):** `meta-webkit` (priority 7)
    wins over poky for `libwpe` (1.16.2 over 1.14.2) and `wpebackend-fdo` (1.14.4 over 1.14.2),
    and over meta-oe at a *lower* version for `highway` (1.0.4 over 1.1.0), `libjxl` (0.8.1 over
    0.10.5), `libvpx` (1.10.0 over 1.14.1), `xdg-dbus-proxy` (0.1.4 over 0.1.5) and `bubblewrap`
    (0.8.0, equal). Of those, `highway`, `libjxl`, `libwpe` and `wpebackend-fdo` are in the image's
    build graph. `meta-wisekiosk` (priority 10) wins `woff2` 1.0.2 over `meta-webkit`'s 1.0.2.
    `meta-webkit` also turns on `icu` in `harfbuzz`'s PACKAGECONFIG for every build (its
    `harfbuzz_%.bbappend`). With `BB_DANGLINGAPPENDS_WARNONLY = "false"` the parse reports no
    dangling append.

## Harness

All one-off and committed beside this README (R2), except where a run names a shipped tool.

- [`p7_min.js`](../gpu_compositing/p7_min.js) — smoothness probe, used unmodified from the
  gpu_compositing investigation.
- `mf-probe.js` — module-fault probe: every 30 s it writes the `MF|` payload to `document.title`.
  `fever` is distinct faulted regions (the marker's `data-region`); it equals distinct faulted
  modules while each region holds one placement.
- `parse_smoothness.py`, `parse_module_fault.py` — payload parsers, each proven by its `_test.py`
  on synthetic payloads.
- `verdict.py` — the go/no-go over the parsed runs, proven by `verdict_test.py`.
- `run-smoothness.sh` — one smoothness capture (`p7_min.js`, 585 s): pre-run screenshot into
  `local/`, retried until it shows the rendered dashboard (below), then the
  [`run-appliance.sh`](../gpu_compositing/run-appliance.sh) sequence with the WPE readback —
  the probe as `KIOSK_PROBE` user script, its `MP|` title lines read from the kiosk
  journal, the 1280x720 VOID rule read from DRM debugfs, `kiosk.conf` restored afterwards. The X
  baseline runs called `run-appliance.sh` itself, at the commit each run header names.
  - **Settle threshold:** the pre-run screenshot must be not blank and have mean luma (0–255, as
    `tools/kiosk-screenshot.sh` reports it) of at least 10, retried every 10 s for up to 120 s,
    else the run is VOID. Calibrated on one frame per class from the X baseline at 1280x720 —
    thin: rendered with cards open 16.06 and 16.35; rendered with three park sources failing
    13.22; clock and date only, modules still loading, 5.24; near-black mid-load 0.008. Whether a
    capture had cards open with data is the operator's call from the kept screenshot.
- `run-soak.sh` — the 1 h soak: `mf-probe.js` as `KIOSK_PROBE` user script, its `MF|` samples read
  from the kiosk journal, then the `kiosk-soak` samples and summary, restarts, boot ids, swap
  counters, PSI and kernel OOM lines for the window. `mf-reader.sh` read the title over X for the
  baseline soak.
- `run-time-to-page.sh` — time to page, three cold boots with one connection each at 120 s: the
  shipped `time-to-page.js` beacon (`meta-wisekiosk/recipes-core/kiosk-bootprof/files/`) titles
  the page `T <epoch_ms>` (`Date.now()`) once the weather glyph renders in its face; time to page
  is that minus the boot epoch read at READ_AT 115. A boot whose journal shows a clock step or
  timesyncd sync later than its time to page is SUSPECT and re-run once. On WPE the beacon runs
  as the `KIOSK_PROBE` user script and the shipped `measure-page.sh` reads its `TITLE` line from
  the journal; the X baseline ran it as surf's `script.js`, read by `time-to-page-x.sh` over X.
  The X image's own `measure-surf.sh` does not apply: its beacon waits on `.module`/`.wi`, which
  the pinned frontend no longer renders.
- `xval-capture.sh`, `xval-judge.sh` — `kiosk-drmgrab` cross-validated against
  `import -window root`: two capture pairs 61 s apart, judged on a static crop (AE = 0, crop rich
  enough to expose a de-tile or channel-order bug) and a clock crop (must change).

## Metrics

Per run, one table per run. None yet.

## Findings

None yet.

## Changes configured as a result

Pending the verdict.
