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
not. If 2.44.4 passes, one attempt is measured at 2.54. The X baseline (S1) is measured and the
WPE image paints and composites on the GPU (S2); no verdict yet.

## Test runs

Every run names its board role and the image commit from `/etc/buildinfo` (R1); every capture is
committed beside this README (R2); no table mixes runs (R3). S1 is the X baseline: bench, image
`20a1f342580a10a0b32f26f4bcb804223ca068b1` (`origin/main` plus the `#185 capture` commits), booted
from slot B. The S1 harness ran from a checkout pinned at `ea79e18`, clean, except time to page
(below).

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
| 10 | bench · Pi Zero W | `20a1f34` | `run-ttp-readat300.sh` (the Run 9 driver with READ_AT 300) | TIMEOUT ×3: same parse bug; boot 1 perturbed |
| 11 | bench · Pi Zero W | `20a1f34` | driver `09b36c2`, `time-to-page-x.sh` `072ea3e` | VOID: killed after the first reboot (concurrent job) |
| 12 | bench · Pi Zero W | `20a1f34` | driver `09b36c2`, `time-to-page-x.sh` `072ea3e` | 20.3–23.3 s, every boot SUSPECT (clock synced after the beacon; pre-fix frame) |
| 13 | bench · Pi Zero W | `20a1f34` | driver `09b36c2`, `time-to-page-x.sh` `70b03c7` | 48.00, 59.63, 50.80 s; no SUSPECT, no re-run |
| 14 | bench · Pi Zero W | `1a8e100` | `kiosk-render-check.sh`, `kiosk-screenshot.sh`, `kiosk-gpu-check.sh` @ `782d4d9` | paint gate passes: advancing, not blank, cog + WPEWebProcess on vc4 |
| 15 | bench · Pi Zero W | `1a8e100` | `kiosk-gpu-check.sh --capture` @ `782d4d9` | `webkit://gpu` aborts cog: no desktop GL |
| 16 | bench · Pi Zero W | `1a8e100` | inline (kiosk.conf edit + journal) | `KIOSK_INSPECTOR=1` loads `file:///` instead of the dashboard |
| 17 | bench · Pi Zero W | `1a8e100` | inline (kiosk.conf edit + journal), render-check @ `782d4d9` | unlisted DRM mode: cog exits 1, systemd restarts it, kiosk.conf restored |
| 18 | bench · Pi Zero W | `32b670c` | render-check, screenshot @ `782d4d9`; inline inspector check | paints; `KIOSK_INSPECTOR=1` loads the dashboard |
| 19 | bench · Pi Zero W | `32b670c` | `run-webgl-query.sh` | WebGL renderer string spoofed ("Apple GPU"): inconclusive |
| 20 | bench · Pi Zero W | `32b670c` | inline (debugfs + `/proc/PID/maps`) | V3D buffers live, `vc4_dri.so` and `renderD128` mapped in WPEWebProcess |
| 21 | bench · Pi Zero W | `32b670c` | `run-s3.sh` → `run-smoothness.sh` @ `32b670c`, `p7_min.js` | VOID: night page state (1 of 4 cards live); stopped mid-capture |
| 22 | bench · Pi Zero W | `32b670c` | `run-time-to-page.sh` @ `32b670c` | 43.36, 40.78, 43.28 s; all pre-step, no SUSPECT, no re-run |
| 23 | bench · Pi Zero W | `32b670c` | `check-coredump.sh`, `check-core-pattern.sh`, `check-baseline-stop-journal.sh` | cores discarded (`core_pattern` `\|/bin/false`); the X baseline boot's 9 stops never dumped |
| 24 | bench · Pi Zero W | `32b670c` | `run-s3-smoothness-soak.sh` → `run-smoothness.sh` @ `786f405`, `p7_min.js` | 52.95 fps, 99.0 % <50 ms, stall 0.0248/s (14 from 13 s); not in the verdict: cog's cache not cleared |
| 25 | bench · Pi Zero W | `32b670c` | as Run 24 | 50.07 fps, 98.3 % <50 ms, stall 0.0654/s (37 from 14 s); not in the verdict, as Run 24 |
| 26 | bench · Pi Zero W | `32b670c` | as Run 24 | 50.10 fps, 98.5 % <50 ms, stall 0.0758/s (43 from 14 s); not in the verdict, as Run 24 |

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
  `time-to-page.js` @ `09b36c2` (sha256 `6ea39079…`) as surf's `script.js`, run from a checkout
  pinned at `09b36c2` with only `time-to-page-x.sh` overlaid from the commit each row names. Run
  10 ran `run-ttp-readat300.sh`, that driver with READ_AT 300, committed here with the bench
  address redacted.
- **Procedure:** three cold boots, one connection each at 120 s, READ_AT 115 (Run 10: 300); a
  SUSPECT boot re-run once (Run 12: all three). Run 10's boot 1 is perturbed: 28 s after its
  reboot command (22:14:07Z), well before the driver's own connection, the operator ran
  `tools/kiosk-screenshot.sh` against bench for an unrelated check (per the operator; not
  annotated in the capture).
- **Raw capture:** `s1-ttp-timeout-readat115.txt` (Run 9), `s1-ttp-timeout-readat300.txt`
  (Run 10), `s1-ttp-void.txt` (Run 11), `s1-ttp-suspect.txt` (Run 12), `s1-ttp-prestep.txt`
  (Run 13).

**Capture notes.** The captures are byte-for-byte as recorded, apart from identity redactions.
The operator's in-file notes name some captures by their working names: "run3b" is
`s1-smoothness-run3.txt`, "VOID-2" is `s1-smoothness-run3-void2.txt`, and
"ttp-baseline-20a1f34-fixed2.txt" is `s1-ttp-suspect.txt`. Where those notes cite an owner ruling,
they mean the plan's page-state rule (cards open with data, a wrong-state capture VOID) and its
fallback (record the best attempt with the state annotated). The helper's two PPM frames from Run 1
are committed as lossless PNG re-encodings for size, made with ImageMagick 7.1.2-31 as
`magick A.ppm s1-xval-A-drmgrab.png` (B likewise). The original PPMs' sha256:

| frame | sha256 of the original PPM |
|---|---|
| A | `1a0ff937951e54cc55d39ed97fbd464ccba0ee917623d51cea496f935728640f` |
| B | `8c39136210def51e3a4a603cf891eb3db6fc6eeea5fb4f4588d37a9e9193b6e4` |

`magick s1-xval-A-drmgrab.png ppm:- | sha256sum` reproduces A's hash byte for byte (B likewise),
so the PNGs carry the PPMs exactly.

### Runs 14–20 — S2, the WPE image paints, bench

- **Board:** bench, Pi Zero W.
- **Image commit:** `1a8e100d31cadb6591a7a3bca01d1879dcec8bf5` (Runs 14–17, slot A) and
  `32b670c5a4379443aef5ddab9ca0e43cac1c5e96` (Runs 18–20, slot B, after the `kiosk-launch` argv
  fix), each from `/etc/buildinfo` in the capture or the run's own header.
- **Scripts deployed:** the shipped `kiosk-render-check.sh`, `kiosk-screenshot.sh` and
  `kiosk-gpu-check.sh` from a host checkout at `782d4d9`; `run-webgl-query.sh` (Run 19), committed
  here with the bench address redacted. Everything else ran as inline commands, not saved as
  scripts — an R2 gap. As the operator reports them:
  - Runs 15, 16, 17 and 18's inspector check: back up kiosk.conf (`cat` over ssh), change it with
    `printf` (append `KIOSK_URL`, set `KIOSK_INSPECTOR=1`, or set
    `COG_PLATFORM_DRM_VIDEO_MODE=9999x9999`), `systemctl restart kiosk`, read the journal, write
    the backup back and `cmp` it; each capture's own step headers ("--- backup ---", "--- seed
    bogus mode, restart ---") are the sequence.
  - Run 15's crash window: `journalctl -u kiosk -b --no-pager | sed -n '/Stopping Kiosk/,/Loaded
    successfully/p'`.
  - Run 18's build check: `grep /etc/buildinfo; rauc status`.
  - Run 20: `cat /sys/kernel/debug/dri/0/bo_stats` and `grep dri /proc/$(pidof
    WPEWebProcess)/maps`.
- **Procedure:**
  - Run 14: the ported render-check at the default crop `560x300+220+20`, a screenshot, and the
    read-only gpu-check; `s2-paint-drmgrab.png` is the first `kiosk-drmgrab` frame taken by hand
    before the tools ran.
  - Run 15: two `--capture` attempts with the tool at `782d4d9` — refused without a `KIOSK_URL`
    line, then, with one added, `kiosk-drmgrab` refused an RG16 framebuffer and the capture failed
    (per the operator, the console's framebuffer while cog restarted after aborting) — then the
    crash window's journal.
  - Run 16: `KIOSK_INSPECTOR=1`, then also an explicit `KIOSK_URL`; kiosk restarted, journal read;
    kiosk.conf restored byte-identical (`cmp`) after each.
  - Run 17: `COG_PLATFORM_DRM_VIDEO_MODE=9999x9999` in kiosk.conf, kiosk restarted; NRestarts and
    the journal read; kiosk.conf restored byte-identical; render-check after.
  - Runs 18–20: render-check and screenshot; `KIOSK_INSPECTOR=1` with the journal read; the WebGL
    renderer queried through the remote inspector; `bo_stats` and WPEWebProcess's mapped `dri`
    lines read.
- **Raw capture:** `s2-paintgate.txt`, `s2-paintgate-screenshot.png`, `s2-paint-drmgrab.png`
  (Run 14); `s2-gpucapture-1.txt`, `s2-gpucapture-2.txt`, `s2-webkitgpu-crash.txt` (Run 15);
  `s2-inspector-file-url.txt`, `s2-inspector-1.txt`, `s2-inspector-2.txt` (Run 16);
  `s2-seeded-failure.txt` (Run 17); `s2-verify-32b670c.txt`, `s2-verify-32b670c-screenshot.png`,
  `s2-inspector-fixed.txt` (Run 18); `s2-webgl-query.txt` (Run 19); `s2-vc4-hwevidence.txt`
  (Run 20). `s2-paint-drmgrab.png` is a lossless PNG of the helper's PPM (sha256
  `0b872997534ce30e6bdc23b27b34107ddb3452f8bd8a5b73ea655a2a2dd9e445`, reproduced by
  `magick s2-paint-drmgrab.png ppm:- | sha256sum`).

### Runs 21–23 — S3, the WPE image measured, bench, commit `32b670c`

- **Board:** bench, Pi Zero W. **Image commit:** `32b670c5a4379443aef5ddab9ca0e43cac1c5e96`,
  slot B, from `/etc/buildinfo` in each capture. Run 23's baseline journal is from the S1 boot
  `44ce604290894ada92bf1734a363a6c0` (image `20a1f34`), read on this image.
- **Scripts deployed:** the drivers committed here, run unmodified from a host checkout at
  `32b670c`. `run-s3.sh` (Run 21) chained three smoothness runs, the soak and time to page; it
  is committed here with the bench address redacted. Run 22's driver was launched on its own by
  an inline command, not saved as a script — an R2 gap. As the operator reports it:

  ```sh
  cd /home/tjwise/meta-wisekiosk-185-s2
  setsid nohup bash -c '
    flock -n "<bench.lock path>" bash -c "
      cd /home/tjwise/meta-wisekiosk-185-s2
      docs/issue_investigation/wpe_evaluation/run-time-to-page.sh root@<BENCH_ADDRESS> S3-32b670c <outpath>
      echo S3_TTP_EXIT=\$?
    " || echo LOCK_HELD_REFUSED
  ' > <logpath> 2>&1 < /dev/null &
  ```

  `check-coredump.sh`, `check-core-pattern.sh` and `check-baseline-stop-journal.sh` (Run 23)
  are read-only and committed here; `poll-cards-open.sh`, a one-shot `kiosk-screenshot.sh` call
  for the page-state wait, likewise. The check after Run 21's stop ran inline, not saved as a
  script — an R2 gap. As the operator reports it: `cat /data/config/kiosk.conf` and `cmp`
  against the pre-run copy.
- **Procedure:**
  - Run 21: the pre-run screenshot passed the settle threshold at 23:28 local, with one of four
    cards live and three parks closed for the night; the operator voided it for page state, as the
    capture's own note says. A TERM to the driver did not stop it while it waited on the capture
    ssh (the Harness section's note on aborting a driver); a TERM to that ssh did, and the EXIT
    trap restored `kiosk.conf`. `run-s3.sh` then started smoothness run 2, which was stopped in its
    pre-run screenshot loop (after one `kiosk-drmgrab` refusal of an RG16 framebuffer) before it
    wrote a capture: one TERM each to that driver, `run-s3.sh`, and its `flock` and `setsid`
    wrappers. Run 3, the soak and the chain's time to page never started. `kiosk.conf` held only
    `KIOSK_INSPECTOR=0` afterwards, byte-identical to the pre-run copy.
  - Run 22: three cold boots, one connection each at 120 s, READ_AT 115; driver exit 0.
  - Run 23: where cores land and how much they take (`check-coredump.sh`), the kernel's core
    handler (`check-core-pattern.sh`), and every kiosk stop in the S1 baseline boot's persistent
    journal (`check-baseline-stop-journal.sh <ssh-target> 44ce604290894ada92bf1734a363a6c0`).
- **Raw capture:** `s3-smoothness-run1-VOID.txt` (Run 21), `s3-ttp.txt` (Run 22),
  `s2-coredump-check.txt`, `s2-core-pattern.txt`, `s2-baseline-stop-journal.txt` (Run 23, named
  by the operator before the S3 numbering). The pre-run screenshots stay in `local/`.

### Runs 24–26 — S3 smoothness, bench, commit `32b670c`

- **Board:** bench, Pi Zero W. **Image commit:** `32b670c5a4379443aef5ddab9ca0e43cac1c5e96`,
  slot B, from `/etc/buildinfo` in each capture.
- **Scripts deployed:** `run-smoothness.sh` and `p7_min.js` unmodified from a host checkout at
  `786f405`, as each capture's harness line records; the driver is byte-identical to `32b670c`'s.
  `run-s3-smoothness-soak.sh`, committed here, chained the three captures and then the soak. It
  was launched by an inline command, not saved as a script — an R2 gap. As the operator reports
  it:

  ```sh
  setsid nohup bash -c '
    flock -n "<bench.lock>" /tmp/.../scratchpad/run-s3-smoothness-soak.sh root@<BENCH_ADDRESS> || echo LOCK_HELD_REFUSED
  ' > <logpath> 2>&1 < /dev/null &
  ```

- **Procedure:** three back-to-back captures, 585 s each, 12:45–13:15Z. Before launch the operator
  checked by eye that all four park cards showed live data, as the chain script's header states;
  each pre-run screenshot passed the settle threshold and is kept in `local/`. 1280x720 was live
  before and after every capture, and NRestarts stayed 0. The stall rate is
  `steady_stall_from_series` over each capture's full `MP|` series: the count runs from the last
  line before 15 s (`ref_t`) to the final line, over the final `sec` − 15.
- **Not in the verdict.** The driver's `rm -rf /home/root/.cache/cog` before each restart removed
  nothing: every capture's readback reports that directory absent and records no bundle. cog's
  cache state was therefore uncontrolled, where the X baseline cleared surf's cache before every
  run, so the procedures differ. The captures stand as recorded and are re-run after the driver
  fix.
- **Raw capture:** `s3-smoothness-run1.txt` (Run 24), `s3-smoothness-run2.txt` (Run 25),
  `s3-smoothness-run3.txt` (Run 26).

## Configuration under test

- **Baseline (X):** the image built from `origin/main` plus the `#185 capture` commits, which add
  only `kiosk-drmgrab` (`meta-wisekiosk/recipes-graphics/kiosk-drmgrab/`) — `20a1f34` on bench.
  Session: `meta-wisekiosk/recipes-core/kiosk-session/` (bare Xorg, `surf` at 1280x720).
- **Bench page configuration:** `config.json` sha256 `767e3d1a…` (every smoothness header), one
  module placement in each of three regions (`s1-placement-counts.txt`, counts only), so
  `fever` counts distinct faulted modules exactly. `park_wait_times.rotation_interval_seconds` is
  absent (schema default).
- **Candidate (WPE):** the `#185 W1` commits on `185-wpe-evaluation`; built as `1a8e100` (Runs
  14–17) and, after the `kiosk-launch` argv fix, `32b670c` (Runs 18–23). `meta-webkit` `scarthgap`
  at `2d29669a3d78e462276044f3f8bde0e4dec33696` (`includes/base.yaml`); `wpewebkit` 2.44.4 with
  `wpebackend-fdo` (the `wpe` block of `kiosk-zero-w.yaml`); `cog -P drm` at 1280x720
  (`meta-wisekiosk/recipes-core/kiosk-session/`) with the `--user-script` patch
  (`meta-wisekiosk/recipes-browser/cog/`).
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

**Aborting a driver:** kill its process group, `kill -TERM -- -<pgid>`. Bench runs launch
drivers with `setsid nohup …`, so each has its own group; `ps -o pgid= -p <driver pid>` prints
it. Killing the group also ends the foreground ssh or sleep, so the EXIT trap restores
`kiosk.conf` at once. A TERM to the driver alone is held until that child returns. In
`run-time-to-page.sh`, an abort while the board is rebooting runs the restore against a board
that is down. The restore fails, and the `kiosk.conf.wpe-bak` or `kiosk.conf.wpe-absent` backup
stays in `/data/config/`. The next run then refuses until that backup is restored by hand.

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

**Run 13** (`s1-ttp-prestep.txt`)

| boot | 1 | 2 | 3 |
|---|---|---|---|
| time to page, s | 48.00 | 59.63 | 50.80 |
| frame | pre-step | post-step | pre-step |
| timesyncd sync, s monotonic | 55.79 | none logged | 55.82 |

**Run 12** (`s1-ttp-suspect.txt`; every value SUSPECT, post-step frame)

| boot | 1 | 1-rerun | 2 | 2-rerun | 3 | 3-rerun |
|---|---|---|---|---|---|---|
| time to page, s | 23.34 | 21.36 | 20.32 | 20.63 | 22.84 | 20.89 |
| timesyncd sync, s monotonic | 57.92 | 55.83 | 55.34 | 65.86 | 57.74 | 56.05 |

**Run 22** (`s3-ttp.txt`)

| boot | 1 | 2 | 3 |
|---|---|---|---|
| time to page, s | 43.36 | 40.78 | 43.28 |
| frame | pre-step | pre-step | pre-step |
| timesyncd sync, s monotonic | 55.71 | 55.64 | 66.29 |

**Run 24** (`s3-smoothness-run1.txt`)

| sec | frames | mean fps | % <50 ms | max ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|---|
| 580 | 30712 | 52.95 | 99.0 | 2353 | 18 | 0.0248/s (14 from ref_t 13 s) | 10 |

**Run 25** (`s3-smoothness-run2.txt`)

| sec | frames | mean fps | % <50 ms | max ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|---|
| 581 | 29091 | 50.07 | 98.3 | 1576 | 45 | 0.0654/s (37 from ref_t 14 s) | 11 |

**Run 26** (`s3-smoothness-run3.txt`)

| sec | frames | mean fps | % <50 ms | max ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|---|
| 582 | 29157 | 50.10 | 98.5 | 2453 | 51 | 0.0758/s (43 from ref_t 14 s) | 12 |

**Run 14** (`s2-paintgate.txt`)

| render-check | screenshot mean | gpu-check | processes on `/dev/dri` |
|---|---|---|---|
| rc 0, advancing | 13.79 | rc 0 | cog (4 fds), WPEWebProcess (7 fds), both `vc4_dri.so`; WPENetworkProcess none |

**Run 20** (`s2-vc4-hwevidence.txt`)

| V3D BOs | V3D shader BOs | binner | dumb | WPEWebProcess maps |
|---|---|---|---|---|
| 14728 kB (11) | 12 kB (3) | 16384 kB (1) | 4052 kB (1) | `vc4_dri.so`; 7 `renderD128` mappings |

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
- **The WPE image paints at 1280x720** (Run 14, again on `32b670c` in Run 18): the ported
  render-check advances, the screenshot is the dashboard, cog drives DRM directly.
- **WPE composites on the GPU.** Run 20: V3D buffer objects are live in `bo_stats`, and
  WPEWebProcess has Mesa's `vc4_dri.so` loaded and seven mappings of `/dev/dri/renderD128`. Run 19's
  WebGL renderer string ("Apple GPU / Apple Inc.") is WebKit's fingerprinting mask, not the
  hardware, so that method is inconclusive.
- **`webkit://gpu` aborts cog on this image** (Run 15): "Couldn't open libGL.so.1 or
  libOpenGL.so.0", SIGABRT, and Restart=always brings the dashboard back. The page needs desktop
  GL, which the image does not carry, so `kiosk-gpu-check.sh --capture` reports itself unavailable
  on WPE (`b30574c`).
- **`KIOSK_INSPECTOR=1` loaded `file:///`** (Run 16) because a bare `--enable-developer-extras`
  takes the following URL as its value (cog's optional-argument settings flags under GLib); fixed
  in `32b670c` by passing `=true`, and Run 18 loads the dashboard with the inspector on.
- **A DRM setup failure restarts the session** (Run 17): an unlisted mode makes cog print
  "Platform setup failed: Failed to initialize DRM" and exit 1 (the carried 0002 patch), and
  systemd's Restart=always retries it (NRestarts 0 → 1); kiosk.conf restored, the render advances
  again.
- **Startup log lines that do not stop the page.** Every cog start these journals show logs
  "EGLDisplay Initialization failed: EGL_NOT_INITIALIZED": WebCore's `PlatformDisplay` logs it
  when its shared display in the UI process fails to initialise, and the page renders afterwards.
  The same starts log "XDG_RUNTIME_DIR is invalid or not set" (up to three times), "Could not
  determine the accessibility bus address" and "Renderer 'modeset' does not support rotation 0".
- **cog crashes on stop; surf did not.** Each `systemctl restart kiosk` in Runs 15 and 17 logs the
  outgoing cog exiting with SIGSEGV ("code=dumped, status=11/SEGV") before the new one starts. In
  the X baseline's boot all nine kiosk stops exit with status 1 and none dumps (Run 23), so the
  defect is specific to the cog + WPE session; the evidence does not isolate which of the two
  crashes. It costs no disk: `core_pattern` is `|/bin/false`, which discards every core, and
  `/var/lib/systemd/coredump/` is empty. systemd's NRestarts does not count these manual restarts,
  so the verdict's restart count does not see them; the defect is outside the verdict rules and is
  recorded, not judged.
- **Time to page on the X baseline: 48.00, 59.63, 50.80 s** (Run 13), recorded, not judged. Runs 9
  and 10 measured nothing: surf prefixes the page title (`@cgDISMfxT:- | T <epoch>`) and
  `time-to-page-x.sh` matched only at the start, fixed in `072ea3e`. Run 12 parsed, but timesyncd's
  initial sync lands at 55–66 s monotonic, after the beacon and before the read, so its values
  (20–23 s) are in the corrected wall-clock frame, not the beacon's; against Run 13's 48–51 s, the
  sync moved the clock forward by about 27 s. `70b03c7` recovers the beacon's frame from the last
  journal entry before the sync (Run 13, boots 1 and 3). Boot 2 logged no sync, and its journal
  frame agreed with the wall clock within 1 s, so its post-step value stands.
- **cog's cache was not cleared in Runs 24–26.** The smoothness driver removes
  `/home/root/.cache/cog`, which does not exist on this image, so each capture ran with cog's cache
  in whatever state the previous run left, and no bundle was recorded. Those runs are kept as
  recorded and do not count toward the verdict.
- **Time to page on WPE: 43.36, 40.78, 43.28 s** (Run 22), recorded, not judged, against the X
  baseline's 48.00, 59.63, 50.80 s (Run 13). Every boot's timesyncd sync (55.6–66.3 s monotonic)
  came after the beacon, so all three are in the beacon's pre-step frame.

## Changes configured as a result

Pending the verdict.
