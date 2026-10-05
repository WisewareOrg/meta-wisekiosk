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
not. If 2.44.4 passes, one attempt is measured at 2.54. The X baseline (S1) is measured; no
verdict yet.

## Test runs

Every run names its board role and the image commit from `/etc/buildinfo` (R1); every capture is
committed beside this README (R2); no table mixes runs (R3). S1 is the X baseline: bench, image
`20a1f342580a10a0b32f26f4bcb804223ca068b1` (`origin/main` plus the `#185 capture` commits), booted
from slot B. The S1 harness ran from a checkout pinned at `ea79e18` (its reflog holds no other
commit), except time to page (below).

| Run | Board (role) | Image commit | Harness / scripts | Result (1 line) |
|---|---|---|---|---|
| 1 | bench · Pi Zero W | `20a1f34` | `xval-capture.sh`, `xval-judge.sh` @ `ea79e18` | PASS: helper = `import` on the static crop in both pairs; grayscale frame |
| 2 | bench · Pi Zero W | `20a1f34` | `run-smoothness.sh` @ `ea79e18` → `run-appliance.sh`, `p7_min.js` | 49.46 fps, 98.6 % <50 ms, stall 0.0252–0.0541/s (bounded) |
| 3 | bench · Pi Zero W | `20a1f34` | as Run 2 | 47.46 fps, 98.0 % <50 ms, stall 0.0252–0.0541/s (bounded) |
| 4 | bench · Pi Zero W | `20a1f34` | as Run 2 | 52.59 fps, 98.7 % <50 ms, stall 0.0253–0.0343/s (bounded); 3 of 4 cards live |
| 5 | bench · Pi Zero W | `20a1f34` | as Run 2 | VOID: pre-run screenshot was a still-loading page |
| 6 | bench · Pi Zero W | `20a1f34` | as Run 2 | VOID: bench rebooted mid-capture by a concurrent job |
| 7 | bench · Pi Zero W | `20a1f34` | as Run 2 | VOID: stopped early; a park source was failing |
| 8 | bench · Pi Zero W | `20a1f34` | `run-soak.sh` + `mf-reader.sh` @ `ea79e18`, `mf-probe.js` | 1 h: fmax 0, fever 0, 0 restarts, 0 reboots, no OOM |
| 9 | bench · Pi Zero W | `20a1f34` | `run-time-to-page.sh` + `time-to-page-x.sh` @ `09b36c2` | TIMEOUT ×3: the harness could not parse surf's prefixed title |
| 10 | bench · Pi Zero W | `20a1f34` | as Run 9, READ_AT 300 (hand-modified driver) | TIMEOUT ×3: same parse bug; boot 1 perturbed |
| 11 | bench · Pi Zero W | `20a1f34` | driver `09b36c2`, `time-to-page-x.sh` `072ea3e` | VOID: killed after the first reboot (concurrent job) |
| 12 | bench · Pi Zero W | `20a1f34` | driver `09b36c2`, `time-to-page-x.sh` `072ea3e` | 20.3–23.3 s, every boot SUSPECT (clock synced after the beacon; pre-fix frame) |
| 13 | bench · Pi Zero W | `20a1f34` | driver `09b36c2`, `time-to-page-x.sh` `70b03c7` | pending: the pre-step-frame re-run |

### Run 1 — capture cross-validation, bench, commit `20a1f34`

- **Board:** bench, Pi Zero W.
- **Image commit:** `20a1f342580a10a0b32f26f4bcb804223ca068b1` (`/etc/buildinfo`, in the capture
  header).
- **Scripts deployed:** `xval-capture.sh`, `xval-judge.sh` — one-off, committed here; shipped
  `kiosk-drmgrab` (`meta-wisekiosk/recipes-graphics/kiosk-drmgrab/`, sha256 in the header).
- **Procedure:** pair A (helper then `import -window root`), 61 s, pair B; judged with static crop
  `600x200+300+100` and clock crop `360x100+60+55`, chosen from these frames.
- **Raw capture:** `s1-xval-capture.txt`, `s1-xval-judge.txt`, `s1-xval-A-import.png`,
  `s1-xval-B-import.png`, and `s1-xval-A-drmgrab.png`, `s1-xval-B-drmgrab.png` — the helper's
  PPMs converted losslessly to PNG for size (AE 0 against the PPMs); `magick X.png X.ppm` restores
  the judge's input.

### Runs 2–7 — smoothness, bench, commit `20a1f34`

- **Board:** bench, Pi Zero W. **Image commit:** `20a1f34…`, in each capture's header.
- **Scripts deployed:** `run-smoothness.sh` @ `ea79e18` (pre-run screenshot, not-blank check only)
  calling [`run-appliance.sh`](../gpu_compositing/run-appliance.sh) unchanged; probe
  [`p7_min.js`](../gpu_compositing/p7_min.js), sha256 `3d0e0c23…` local and deployed.
- **Procedure:** `run-appliance.sh` with prefix `MP`, 585 s, xprop `-len 20000`; cache cleared and
  kiosk restarted before each; 1280x720 live before and after (VOID rule). Page state from the
  pre-run screenshot kept in `local/`: Runs 2 and 3 cards open with data; Run 4 cards open, card 2
  of 4 showing "the source did not answer in time" on this and the two checks before it, recorded
  as the best attempt with the state annotated; mean luma 14.86, checked by hand against the
  settle threshold. Run 5's screenshot was a still-loading page (mean 0.008); Run 6 self-voided on
  the display-mode check after a concurrently launched time-to-page job rebooted bench; Run 7 was
  stopped before readback with the same source failing.
- **Raw capture:** `s1-smoothness-run1.txt`, `-run2.txt`, `-run3.txt` (Runs 2–4) and
  `s1-smoothness-run3-void1.txt`, `-void2.txt`, `-void3.txt` (Runs 5–7).

### Run 8 — 1 h soak, bench, commit `20a1f34`

- **Board:** bench, Pi Zero W. **Image commit:** `20a1f34…` (header); boot id unchanged start to
  end.
- **Scripts deployed:** `run-soak.sh` and `mf-reader.sh` @ `ea79e18` (title read over X every
  30 s); `mf-probe.js`, sha256 `c3f20aa9…`; shipped `kiosk-soak` (5-minute timer).
- **Procedure:** probe as surf's `script.js`, cache cleared, kiosk restarted, 3600 s + 60 s, then
  the MF| log, the `kiosk-soak` samples and summary for the window, NRestarts, boot ids, swap
  counters, PSI and kernel OOM lines.
- **Raw capture:** `s1-soak.txt`.

### Runs 9–13 — time to page, bench, commit `20a1f34`

- **Board:** bench, Pi Zero W. **Image commit:** `20a1f34…`, recorded per boot.
- **Scripts deployed:** the X driver `run-time-to-page.sh` @ `09b36c2` with
  `time-to-page.js` @ `09b36c2` (sha256 `6ea39079…`) as surf's `script.js`, and the harness
  `time-to-page-x.sh` at the commit each row names. Run 10 ran a hand-modified copy of the driver
  with READ_AT 300 that was not committed — an R2 gap, harmless only because every boot
  TIMEOUT'd on the parse bug.
- **Procedure:** three cold boots, one connection each at 120 s, READ_AT 115 (Run 10: 300); a
  SUSPECT boot re-run once (Run 12: all three). Run 10's boot 1 was perturbed by the operator's own
  screenshot checks (per the operator's handoff; not annotated in the capture).
- **Raw capture:** `s1-ttp-timeout-readat115.txt` (Run 9), `s1-ttp-timeout-readat300.txt`
  (Run 10), `s1-ttp-void.txt` (Run 11), `s1-ttp-suspect.txt` (Run 12); Run 13 pending.

## Configuration under test

- **Baseline (X):** the image built from `origin/main` plus the `#185 capture` commits, which add
  only `kiosk-drmgrab` (`meta-wisekiosk/recipes-graphics/kiosk-drmgrab/`) — `20a1f34` on bench.
  Session: `meta-wisekiosk/recipes-core/kiosk-session/` (bare Xorg, `surf` at 1280x720).
- **Bench page configuration:** `config.json` sha256 `767e3d1a…` (every smoothness header), one
  module placement in each of three regions (`s1-placement-counts.txt`, counts only), so
  `fever` counts distinct faulted modules exactly. `park_wait_times.rotation_interval_seconds` is
  absent (schema default).
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
  is that minus the boot epoch read at READ_AT 115 (`frame=post-step`). When the journal shows a
  clock step or timesyncd sync later than the time to page, the beacon stamped the earlier
  frame, and the boot epoch comes from the last journal entry before the step
  (`frame=pre-step`). Placing the step against the uncorrected time to page cannot misplace the
  beacon for a forward step, the only kind here (the clock restores the shutdown time, so it is
  always behind): a beacon before the step gives beacon − step < step, one after gives
  beacon > step; only a backward step could. A boot is SUSPECT only with no entry before the
  step, or with no step and the two frames more than 1 s apart; a SUSPECT boot is re-run once.
  On WPE the beacon runs as the `KIOSK_PROBE` user script and the shipped `measure-page.sh` reads
  its `TITLE` line from the journal; the X baseline ran it as surf's `script.js`, read by
  `time-to-page-x.sh` over X.
  The X image's own `measure-surf.sh` does not apply: its beacon waits on `.module`/`.wi`, which
  the pinned frontend no longer renders.
- `xval-capture.sh`, `xval-judge.sh` — `kiosk-drmgrab` cross-validated against
  `import -window root`: two capture pairs 61 s apart, judged on a static crop (AE = 0, crop rich
  enough to expose a de-tile or channel-order bug) and a clock crop (must change).

## Metrics

Smoothness from `parse_smoothness.py` over each capture's last `MP|` line; time windows are the
probe's own (570 s of the 585 s capture).

**Run 2** (`s1-smoothness-run1.txt`)

| sec | frames | mean fps | % <50 ms | max ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|---|
| 570 | 28191 | 49.46 | 98.6 | 1900 | 30 | bounded 0.0252–0.0541/s (14–30) | 11 |

**Run 3** (`s1-smoothness-run2.txt`)

| sec | frames | mean fps | % <50 ms | max ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|---|
| 570 | 27052 | 47.46 | 98.0 | 1486 | 30 | bounded 0.0252–0.0541/s (14–30) | 11 |

**Run 4** (`s1-smoothness-run3.txt`)

| sec | frames | mean fps | % <50 ms | max ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|---|
| 569 | 29921 | 52.59 | 98.7 | 1298 | 19 | bounded 0.0253–0.0343/s (14–19) | 14 |

**Run 8** (`s1-soak.txt`; MF| from `parse_module_fault.py`, 117 samples)

| fmax | fever | umax | restarts | reboots | OOM lines | min MemAvailable | rss_total | swap in/out | PSI |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | 232 MB | 180168 → 227332 kB, slope +51281 kB/h (n=12) | 0 / 0 | unavailable |

**Run 12** (`s1-ttp-suspect.txt`; every value SUSPECT, post-step frame)

| boot | 1 | 1-rerun | 2 | 2-rerun | 3 | 3-rerun |
|---|---|---|---|---|---|---|
| time to page, s | 23.34 | 21.36 | 20.32 | 20.63 | 22.84 | 20.89 |
| timesyncd sync, s monotonic | 57.92 | 55.83 | 55.34 | 65.86 | 57.74 | 56.05 |

## Findings

- **The capture helper reads what X shows.** Run 1: `kiosk-drmgrab` and `import -window root`
  agree pixel for pixel on the static crop in both pairs, and the clock crop differs between the
  pairs, so the helper is reading the live scanout, de-tiled correctly. The page is grayscale
  (R=G=B everywhere), so channel order is unverifiable on it.
- **The X baseline's smoothness range.** Every run's stall count is bounded (more than 14 stalls,
  all 14 retained at t ≥ 15 s), so the verdict's baseline is BL 0.0253/s, BU 0.0541/s; % <50 ms
  minimum 98.0; mean fps minimum 47.46.
- **Module faults: none.** fmax and fever are 0 through the hour, so any candidate fault is a
  regression under the verdict.
- **Stability: clean.** No restart, no reboot, no OOM line in the hour.
- **Memory, recorded not judged.** rss_total rose 180 → 227 MB over the 0.9 h window (slope
  +51 MB/h over 12 samples); min MemAvailable 232 MB; no swap. One hour cannot show a leak
  (`surf_memory_soak/README.md`). PSI is unavailable: `/proc/pressure/memory` does not exist on
  this kernel.
- **`kiosk-soak` reports "throttled 12 sample(s)" falsely.** Every sample has `thr=unknown` (no
  `vcgencmd` on the image), and the summary counts anything but `0x0` as throttled. It is not a
  throttling observation.
- **One MF| sample is missing** (t 1086 → 1146 s): one 30 s read found no title.
- **`systemctl reboot` prints an error and reboots anyway.** Every time-to-page boot logged "Call to
  Reboot failed: Unit dbus-org.freedesktop.login1.service failed to load properly … File exists"
  (logind is masked), yet each boot has a new boot id and read at ~115 s.
- **Time to page, so far.** Runs 9 and 10 measured nothing: surf prefixes the page title
  (`@cgDISMfxT:- | T <epoch>`) and `time-to-page-x.sh` matched only at the start, fixed in
  `072ea3e`. Run 12 parsed, but timesyncd's initial sync lands at 55–66 s monotonic, after the
  beacon and before the read, so every value is in the wrong wall-clock frame; `70b03c7` recovers
  the beacon's frame. The beacon fires ~20–23 s into the boot. Run 13 is the measurement.

## Changes configured as a result

Pending the verdict.
