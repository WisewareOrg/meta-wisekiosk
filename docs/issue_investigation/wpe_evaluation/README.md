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
| 27 | bench · Pi Zero W | `32b670c` | `run-s3-smoothness-soak.sh` → `run-soak.sh` @ `786f405`, `mf-probe.js` | VOID: stopped early, cog's cache not cleared |
| 28 | bench · Pi Zero W | `32b670c` | `check-stall-correlation.sh` | Runs 24–26's first 90 s: no backend line, no periodic cog or WPE line |
| 29 | bench · Pi Zero W | `32b670c` | `check-cog-cache-path.sh` | cog's cache is `/home/root/.cache/wpe`; no `.cache/cog`; no HOME or XDG_* in cog's environment |
| 30 | bench · Pi Zero W | `32b670c` | `check-cog-cache-resolver.sh` @ `cd916b0` | resolves `/home/root/.cache/wpe`, 24 entries |
| 31 | bench · Pi Zero W | `32b670c` | `run-s3-smoothness-soak.sh` → `run-smoothness.sh` @ `cd916b0`, `p7_min.js` | 50.72 fps, 98.8 % <50 ms, stall 0.0795/s (45 from 13 s) |
| 32 | bench · Pi Zero W | `32b670c` | as Run 31 | 52.83 fps, 99.1 % <50 ms, stall 0.0673/s (38 from 14 s) |
| 33 | bench · Pi Zero W | `32b670c` | as Run 31 | 55.89 fps, 99.5 % <50 ms, stall 0.0035/s (2 from 14 s) |
| 34 | bench · Pi Zero W | `32b670c` | `run-s3-smoothness-soak.sh` → `run-soak.sh` @ `cd916b0`, `mf-probe.js` | 1 h: fmax 0, fever 0, 0 restarts, 0 reboots, no OOM |
| 35 | bench · Pi Zero W | `f4d4bb8` | `run-smoothness.sh` @ `635af22`, `p7_min.js` | 48.45 fps, 97.9 % <50 ms, stall 0.0246–0.0423/s (bounded); cards judged by eye |
| 36 | bench · Pi Zero W | `f4d4bb8` | as Run 35 | 48.82 fps, 98.4 % <50 ms, stall 0.0248–0.0478/s (bounded); cards judged by eye |
| 37 | bench · Pi Zero W | `f4d4bb8` | as Run 35 | 48.71 fps, 98.3 % <50 ms, stall 0.0248–0.0496/s (bounded); cards judged by eye |
| 38 | bench · Pi Zero W | `f4d4bb8` | `run-soak.sh` @ `635af22`, `mf-probe.js` | VOID: stopped deliberately right after start, reordered ahead of Run 39 |
| 39 | bench · Pi Zero W | `f4d4bb8` | inline (kiosk.conf edit + journal); driver not saved, an R2 gap | `KIOSK_COG_FEATURES=-AcceleratedCompositing` crash-loops the renderer (SIGSEGV); no capture ran |
| 40 | bench · Pi Zero W | `f4d4bb8` | `run-smoothness.sh` @ `635af22`, `p7_min.js`, `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` | 45.61 fps, 96.7 % <50 ms, stall 0.0247–0.2703/s (bounded) |
| 41 | bench · Pi Zero W | `f4d4bb8` | as Run 40 | VOID: owner saw the panel flashing, stopped by hand; the attribution to CPU rendering is RETRACTED (Runs 44–45) |
| 42 | bench · Pi Zero W | `f4d4bb8` | `run-burst-capture.sh`; `analyze_burst.py`, `analyze_burst2.py`, `cross_match.py` | rc 0 both phases; zero reverts, zero cross-matches under any hash rule; image predates `kiosk-drmgrab --report` |
| 43 | bench · Pi Zero W | `449e571` | `run-burst-capture-v2.sh`, `analyze_burst_v2.py` | rc 0 both phases; fb ids {96,98}, tear 14/60 control, 23/120 cpu; copy_ms median 173.5/173.0; zero reverts |
| 44 | bench · Pi Zero W | `449e571` | `run-burst-capture-v3-control.sh`, `analyze_burst_v3.py` | 12 bursts, disagreeing tiles 1–64 (35,62,27,64,50,48,17,18,42,34,1,42), 52 persistent |
| 45 | bench · Pi Zero W | `449e571` | `run-burst-capture-v3.sh` (cpu phase), `analyze_burst_v3.py` | 12 bursts, disagreeing tiles 0–75, 69 persistent (56 late-change-excluded) |
| 46 | bench · Pi Zero W | `5ec7f0e` | `run-burst-capture-v3-control.sh`, `analyze_burst_v3.py` | 12 bursts, disagreeing tiles 0 throughout, 0 persistent |
| 47 | bench · Pi Zero W | `138d914` | `diagnose-settle-138d914.sh` + the OTA verify's own settle poll | settle oscillated 5.47–7.73 for >3 min post-boot (ABORT at 3:54); 16.43 by +15:56, no faults |
| 48 | bench · Pi Zero W | `138d914` | `sanity-fwgrab.sh` | `kiosk-fwgrab` and `kiosk-drmgrab --report` agree on content (mean 12.29 vs 12.26); ~130 ms |
| 49 | bench · Pi Zero W | `138d914` | `run-fw-burst-capture.sh`, `analyze_fw_burst.py` | fw: 0 flips/90 frames (ms median 129); drmgrab same window: 44 flips, 0 tiles≥3 |
| 50 | bench · Pi Zero W | `5ec7f0e` | `run-load-experiment.sh` | VOID: `kiosk-fwgrab` is absent on 2.44.4 (rc 127); 0 usable frames, all three phases |
| 51 | bench · Pi Zero W | `138d914` | `run-load-experiment.sh` | idle 284 flips/64 tiles≥3; spinner 120/24; drmloop 6/0 |
| 52 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` UNSET (B0), `analyze_burst_v3.py` + `analyze_fw_burst.py` | [33,77,50,0,24,16]; fw 631 |
| 53 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` `-UseDamagingInformationForCompositing` (T1) | v3 all 0; fw CRASHED, no count (not P6) |
| 54 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` `-PropagateDamagingInformation` (T2) | v3 all 0; fw VOID (tmpfs full mid-transfer; re-analyzed offline, 0/90 usable) |
| 55 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` `-UnifyDamagedRegions` (T3) | VOID: 6/6 bursts corrupted (tmpfs full); fw VOID |
| 56 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` UNSET (B1) | 4/6 bursts VOID (0 frames); [VOID,VOID,VOID,VOID,25,25]; fw 38 |
| 57 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` all three combined (T4) | [0,1,0,0,0,0]; fw 1 |
| 58 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` `-UseSkiaForComposition` (T5) | [46,0,25,15,43,60]; fw 182 |
| 59 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` UNSET (B2) | [16,25,61,28,25,0]; fw 24 |
| 60 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` `-UseDamagingInformationForCompositing` rerun (T1) | all 0; fw 0 |
| 61 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` `-PropagateDamagingInformation` rerun (T2) | all 0; fw 1 |
| 62 | bench · Pi Zero W | `138d914` | `run-feature-trial.sh` `-UnifyDamagedRegions` rerun (T3) | [29,15,72,35,6,27]; fw 104 |
| 63 | bench · Pi Zero W | `138d914` | `kiosk-render-check.sh` (V1, default); driver bug | VOID: `label: unbound variable` aborted before any series ran |
| 64 | bench · Pi Zero W | `138d914` + `KIOSK_COG_FEATURES=-UseDamagingInformationForCompositing` | `kiosk-render-check.sh` (V2); same driver bug | VOID: same crash, no data |
| 65 | bench · Pi Zero W | `138d914` → `5ec7f0e` (OTA) | `ota-verify-5ec7f0e.sh` (V3) | FAILED: network reset at 72 % install, rc=255; rebooted, fell back to `138d914` (slot A), BOOT_B_LEFT=0 |
| 66 | bench · Pi Zero W | `d97d6fe` | `ota-verify-d97d6fe.sh` | OTA confirmed; cog argv carries `--features=-UseDamagingInformationForCompositing` by default, no `KIOSK_COG_FEATURES` set |
| 67 | bench (offline) | stored bursts (Runs 52–62) | `validate-render-check-stale.py`, pre-`646c513` | 0 false positives on clean data; 3 `rc=2` could-not-tell results, one a genuine stale miss |
| 68 | bench (offline) | stored bursts (Runs 52–62) | `validate-render-check-stale.py`, post-`646c513` | 12/12 clean bursts rc 0; the miss now rc 3 (stale_tiles=24); the other two resolve to rc 0 |
| 69 | bench · Pi Zero W | `d97d6fe` | `kiosk-render-check.sh` ×5 (V4, default) | 165/165 rc lines 0; no STALE verdict |
| 70 | bench · Pi Zero W | `d97d6fe` + `KIOSK_COG_FEATURES=UseDamagingInformationForCompositing` | `kiosk-render-check.sh` ×5 (V1′) + `run-v3-short.sh` ×1 | 165/165 rc lines 0; independent burst: 10 disagreeing tiles (vs 16–77 on default) |
| 71 | bench · Pi Zero W | `d97d6fe` (± override) | `kiosk-render-check.sh` ×5 each (V4b, V1b; re-sequenced repeat) | 165/165 rc lines 0 both conditions |
| 72 | bench · Pi Zero W | `d97d6fe` → `5ec7f0e` (OTA, under lock) | live proof against the pre-fix image | not yet run as of this snapshot |
| 73 | bench · Pi Zero W | `d97d6fe` | `run-s4-smoothness.sh` @ `635af22`, `smoothness-cards-probe.js` | 50.95 fps, 98.4 % <50 ms, stall 0.0248–0.0460/s (bounded); gate VOID / reclassified LIVE |
| 74 | bench · Pi Zero W | `d97d6fe` | as Run 73 | 51.18 fps, 98.3 % <50 ms, stall 0.0247–0.0459/s (bounded); gate VOID / reclassified LIVE |
| 75 | bench · Pi Zero W | `d97d6fe` | as Run 73 | 50.95 fps, 98.3 % <50 ms, stall 0.0248–0.0442/s (bounded); gate VOID / reclassified LIVE |
| 76 | bench · Pi Zero W | `d97d6fe` | `run-s4-soak.sh` @ `635af22`, `soak-cards-probe.js` | 1 h: fmax 0, fever 0, 0 restarts, 0 reboots, no OOM; cards l=3 then l=2; reclassifier's VOID does not apply |
| 77 | bench · Pi Zero W | `138d914` | `kiosk-render-check.sh` ×5 + `run-v3-short.sh` ×1 (V1-real) | 165/165 rc 0, stale tiles=0; independent burst 0 disagreeing tiles (vacuous, testable_tiles=0); after hours, 2/4 cards |

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
  `s3-smoothness-run3.txt` (Run 26). The operator's scratch copies were later renamed
  `*-VOID-cache.txt` and given an appended VOID note; the files here are the bytes as captured.

### Runs 27–34 — S3 with cog's cache cleared, bench, commit `32b670c`

- **Board:** bench, Pi Zero W. **Image commit:** `32b670c5a4379443aef5ddab9ca0e43cac1c5e96`,
  slot B, from `/etc/buildinfo` in each capture.
- **Scripts deployed:** `run-soak.sh` @ `786f405` (Run 27) and `run-smoothness.sh`, `run-soak.sh`
  and `cog-cache.sh` @ `cd916b0` (Runs 31–34), run unmodified, as each capture's harness line
  records; `check-cog-cache-resolver.sh` @ `cd916b0` (Run 30). `check-stall-correlation.sh`
  (Run 28) and `check-cog-cache-path.sh` (Run 29) are read-only and committed here.
  Runs 27 and 31–34 ran from `run-s3-smoothness-soak.sh`, unchanged, launched as for Runs 24–26
  (an inline command, an R2 gap); for Runs 31–34 the operator first moved the host checkout to
  `cd916b0`. Run 30's header lines came from an inline wrapper around the committed script, not
  saved as a script — an R2 gap. As the operator reports it:

  ```sh
  {
    echo "# check-cog-cache-resolver.sh root@<BENCH_ADDRESS>, harness cd916b0, board role: bench"
    tools/kiosk-ssh.sh root@<BENCH_ADDRESS> 'grep "^meta-wisekiosk " /etc/buildinfo; rauc status 2>&1 | grep "Booted from"'
    docs/issue_investigation/wpe_evaluation/check-cog-cache-resolver.sh root@<BENCH_ADDRESS>
  } > s3-cache-resolver-check.txt
  ```

- **Procedure:**
  - Run 27: the 1 h soak that followed Runs 24–26 in their chain, with the same no-op cache clear;
    stopped early by killing its process group once the defect was confirmed. Its EXIT trap
    restored `kiosk.conf`, which the operator then compared byte-identical to the pre-run copy. It
    holds no `MF|` data.
  - Run 28: for each of Runs 24–26, 90 s of the `kiosk` and `wisekiosk` journals from the
    capture's restart, short-monotonic. The restart times are hard-coded in the script.
  - Run 29: where cog's cache is, read on the board: root's passwd entry, the unit's environment,
    the running cog's HOME and XDG_*, `/root/.cache` and `/home/root/.cache`, and every `cog`
    directory. `getent` is absent on this image, so its section is empty.
  - Run 30: the resolver's answer on the board before the re-run, deleting nothing.
  - Runs 31–33: three captures as Runs 24–26, with each capture's first clear emptying
    `/home/root/.cache/wpe` (24, 24 and 21 entries) and the bundle recorded
    (`index-CDN2Arem.js`). 1280x720 was live before and after each, and NRestarts stayed 0.
  - Run 34: the soak. Its clear before the restart found no cache dir: the cache was cold, cleared
    by Run 33's restore at 14:13:43Z, and the dir was not yet recreated. The soak deployed the
    same second.
- **Raw capture:** `s3-soak-VOID-cache.txt` (Run 27, with the operator's appended notes),
  `s3-stall-correlation-run1.txt` … `-run3.txt` (Run 28), `s2-cog-cache-path.txt` (Run 29, named
  before the S3 numbering), `s3-cache-resolver-check.txt` (Run 30),
  `s3-rerun-smoothness-run1.txt` … `-run3.txt` (Runs 31–33), `s3-rerun-soak.txt` (Run 34).

### Runs 35–41 — S4, pre-fix exploration, bench, commit `f4d4bb8`

- **Board:** bench, Pi Zero W. **Image commit:** `f4d4bb85a317ca6f693487fa042121ff15c24402`,
  slot A, from each capture's own header; the morning's 2.54 image, before
  `kiosk-drmgrab --report` (Run 42 onward) and before `kiosk-fwgrab` (Runs 47 onward) existed.
- **Scripts deployed:** `run-smoothness.sh` and `run-soak.sh`, unmodified, pinned at
  `635af22c3b97af1bd9c4080f24dd730cf6500198` (each capture's own `# harness` line) —
  the same drivers S3 used, with `role=S4-…` and, for Runs 40–41, `kiosk.conf`'s
  `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` added before deploy. Run 39's attempt
  (`KIOSK_COG_FEATURES=-AcceleratedCompositing`) ran from a driver named in its own capture header,
  `run-s4-nocompositing-smoothness.sh`, that was not saved — an R2 gap; as the operator reports it,
  the sequence is backup kiosk.conf, append the feature, restart, read the journal, confirm the
  page renders.
- **Procedure:** Runs 35–37 are three back-to-back 585 s smoothness captures on the plain default
  page, cache cleared and kiosk restarted before each, 1280x720 live before and after; card state
  was read by eye from the pre-run screenshot (the mechanical cards-live gate did not exist yet —
  see Runs 73–76 below). Run 38 started the 1 h soak, then was killed deliberately a few seconds in
  (`kill -TERM -- -<pgid>`) to run Run 39 first, while park hours still held; its EXIT trap
  restored `kiosk.conf`, independently confirmed byte-identical. Run 39's restart logs a renderer
  crash-and-reload loop within 4 s (`WPEWebProcess::requestFrame(): A frame callback was already
  installed.` on both the first and second load, each followed by `Crash!: The renderer process
  crashed.`), ending `kiosk.service: Main process exited, code=dumped, status=11/SEGV`; the
  automated page-render check then failed (`kiosk-drmgrab: unsupported format RG16`), and the
  script aborted before any smoothness capture, restoring `kiosk.conf`. Run 40 is a complete
  585 s capture under CPU rendering; Run 41, the next back-to-back capture under the same
  condition, was stopped by hand on the owner's direct observation of visible flashing on the
  physical panel — not caught by the automated render-check, which only checks non-blank, not
  visual correctness. Its outer script was killed mid-loop, so its own final restore never ran;
  `kiosk.conf` was restored by hand from the saved backup and `cmp`-verified identical to the
  known-good baseline, with a post-restore screenshot confirming the dashboard back to normal.
- **Raw capture:** retained off-tree (captures hold the bench address and absolute host paths;
  see "Redacted harness scripts" below). Parsed with `parse_smoothness.py`; see Metrics.

### Runs 42–43 — S4, the capture-revert instrument, bench

- **Board:** bench, Pi Zero W. **Image commit:** `f4d4bb85a317ca6f693487fa042121ff15c24402`
  (Run 42) then `449e571494ee5d2e393a54dba531b8ddd124c975` (Run 43, after an OTA that adds
  `kiosk-drmgrab --report`), each from the capture's own header.
- **Scripts deployed:** `run-burst-capture.sh` (Run 42) and `run-burst-capture-v2.sh` (Run 43),
  run unmodified; `analyze_burst.py`, `analyze_burst2.py` and `cross_match.py` against Run 42's
  data, `analyze_burst_v2.py` against Run 43's. No capture self-stamps a harness commit the way
  `run-smoothness.sh` does — an R2-adjacent gap shared by every driver in Runs 42–72.
- **Procedure:** each run takes a 60-frame control burst and, after switching
  `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` on and restarting, one or more 60-frame CPU-rendering
  bursts (Run 43 takes two, 120 frames combined), on a hand-picked crop and, for Run 43, the
  render-check default crop (`560x300+220+20`). A "revert" is a strict A,B,A triplet in the
  crop's content hash, anchored two frames back (`analyze_burst2.py`); `cross_match.py` adds,
  for every revert frame, full within-run provenance and a cross-run exact-hash search against
  the other phase's frames; `full_cross_match.py` repeats the search over every frame pair, not
  only revert frames, on both the crop and the full 1280x720 PPM. None of the four found a match
  anywhere, in either run: the whole-crop exact-hash revert rule does not separate the two
  rendering conditions and does not fire on this page, whose content changes continuously. Run 43
  adds `kiosk-drmgrab --report`'s own per-capture numbers (fb id before/after the copy, copy time):
  two scanout framebuffers throughout (ids 96 and 98), copy time median 173.5 ms (control) /
  173.0 ms (cpu), and the scanout fb changing between the before- and after-read 14/60 times in
  the control phase and 23/120 in the cpu phase (23 % / 19 %, not a fixed fraction). Both
  instruments are rejected as stale-content detectors; the `--report` numbers carry forward as
  the mechanism Runs 44–72 build on.
- **Raw capture:** retained off-tree.

### Runs 44–46 — S4, the v3 tile analysis, bench

- **Board:** bench, Pi Zero W. **Image commit:** `449e571494ee5d2e393a54dba531b8ddd124c975`
  (Runs 44–45) and `5ec7f0e5bac8660bf407fd68bd1b96b7df6daba1` (Run 46, the 2.44.4 reference),
  each from the capture's own header.
- **Scripts deployed:** `run-burst-capture-v3-control.sh` (Runs 44, 46) and
  `run-burst-capture-v3.sh` (Run 45's cpu-rendering phase), run unmodified; `analyze_burst_v3.py`
  against each run's 12 x (15-frame) burst series. Every 1280x720 frame is tiled 40x40 px (32x18,
  576 tiles); among a burst's STABLE captures (`fb_before == fb_after`) grouped by scanned-out fb id,
  a tile "disagrees" when the two fb groups differ there (mean abs diff > 1); "persistent" is a
  tile disagreeing in >= 2 consecutive bursts across the run. A first pass over Run 44's data,
  `analysis-v3.log`, sorted burst directories lexically (`control-10` before `control-2`), so its
  printed series and its 48-persistent-tile count are RETRACTED; the natural-order rerun,
  `analysis-v3-fixed.log`, is the number this README reports.
- **Procedure:** Run 44 (control, default rendering): 12 bursts, disagreeing-tile counts
  `[35, 62, 27, 64, 50, 48, 17, 18, 42, 34, 1, 42]`, 52 tiles persistent (same with and without
  late-change exclusion), in four bounding regions. Run 45 (the same 12-burst series' cpu-rendering
  phase): `[0, 24, 29, 60, 75, 26, 38, 50, 19, 16, 25, 35]`, 69 persistent raw / 56 persistent with
  one burst's late-content-change artifact excluded (that burst's count drops 75 -> 0). Run 46
  (2.44.4, same instrument, same board): all 12 bursts disagreeing_tiles=0, 0 persistent; one
  burst (8) has testable_tiles=0 (the two fb ids never co-occurred as stable captures in it, a
  vacuous zero, not a tested-and-clean result). Runs 44 and 45 together retract Run 41's
  CPU-rendering attribution (fact 1): the default-rendering control burst disagrees on as many
  tiles, in the same regions, as the cpu-rendering phase — the stale content is present under
  default rendering on this image, and Run 46 shows it is absent on 2.44.4 under the same
  instrument, which is the first evidence pinning the defect to 2.54 rather than to any rendering
  mode.
- **Raw capture:** retained off-tree.

### Runs 47–51 — S4, kiosk-fwgrab and the load experiment, bench, commit `138d914`

- **Board:** bench, Pi Zero W. **Image commit:** `138d9142b2cff9c59cd0a755595bc3a82db7e3e3`
  (Runs 47–49, 51) and `5ec7f0e5bac8660bf407fd68bd1b96b7df6daba1` (Run 50), each from the
  capture's own header or OTA-verify log.
- **Scripts deployed:** `diagnose-settle-138d914.sh` (Run 47), `sanity-fwgrab.sh` (Run 48),
  `run-fw-burst-capture.sh` + `analyze_fw_burst.py` (Run 49), `run-load-experiment.sh` (Runs
  50–51), run unmodified.
- **Procedure:** Run 47 is the settle check after the OTA to `138d914`: the pre-run screenshot's
  mean luma oscillated 5.47–7.73 across twelve ~14 s polls from +1:16 to +3:54 after boot, below
  the settle threshold throughout, and the OTA-verify script's own gate aborted (`settle rc=1`) at
  +3:54; a later check on the same boot, at roughly +15:56, read 16.43 (fwgrab and drmgrab agree,
  16.32/16.33) and needed no recovery. The kiosk journal for this boot shows no error or crash
  anywhere; the page simply fills slowly on this image. Run 48 cross-validates `kiosk-fwgrab`
  (a VideoCore dispmanx snapshot, no fb id, timed externally) against `kiosk-drmgrab --report`
  immediately after: fwgrab mean 12.29, drmgrab fb_before=fb_after=98 copy_ms=144 mean 12.26 —
  matching content. Run 49 tiles a 90-frame fwgrab burst (the same 40x40 px grid) with the "flip"
  rule — a tile A,B,A across three consecutive frames — and finds 0 flips (ms median 129), against
  44 scanout-side flips (0 at >= 3 tiles) over the same window on drmgrab. Run 50 is the same
  three-phase (idle / spinner / drmloop) load experiment attempted on 2.44.4: `kiosk-fwgrab` does
  not exist on that image (every batch rc=127, "command not found"), so all three phases are VOID,
  0 usable frames — the draft fact list's "load experiment" numbers do not come from this image.
  Run 51 is the same three phases on `138d914`: idle 284 total flips, 64 tiles with >= 3 flips (6
  of 88 frames comparable); spinner 120 flips, 24 tiles >= 3 (5 of 88); drmloop 6 flips, 0 tiles
  >= 3 (1 of 88) — flips occur at rest as well as under load, which does not support a CPU-load
  cause, though no script states that conclusion directly.
- **Raw capture:** retained off-tree.

### Runs 52–62 — S4, the `KIOSK_COG_FEATURES` trials, bench, commit `138d914`

- **Board:** bench, Pi Zero W. **Image commit:** `138d9142b2cff9c59cd0a755595bc3a82db7e3e3`
  throughout, confirmed by `ota-verify-138d914.log`/`ota-verify-138d914-2.log`: the OTA to
  `138d914` lands at roughly 15:40 local, and `d97d6fe` does not build until roughly 18:06, well
  after this chain (and its reruns) completes. No individual capture in this chain prints its own
  buildinfo line, so this is read off the surrounding OTA/build logs rather than per row.
- **Scripts deployed:** `run-feature-trial.sh`, run unmodified, one call per row: six 15-frame
  `analyze_burst_v3.py` bursts plus one 90-frame `analyze_fw_burst.py` burst per trial, read
  fail-closed (a burst that cannot be parsed VOIDs that burst, not the whole trial).
- **Procedure:** B0, T1–T3, B1, T4, T5, B2 ran as one chain (`fix-trials.log`); a host `/tmp`
  tmpfs filled mid-chain during T2's fw transfer and corrupted T3's capture outright. T1
  (`-UseDamagingInformationForCompositing`) is the only single-flag trial that reads clean both
  ways: v3 all zero, fw crashed in the original pass (`analyze_fw_burst.py`: "not P6", on the
  tmpfs-corrupted frames) and reads 0 on the rerun. T2 and T3's original numbers are RETRACTED in
  part: T2's "partial" fw count is a VOID-aware re-analysis of the same corrupted capture
  (`T3-void-check.log`/`BT-void-check.log`), not a new one, and T3's original six-burst series
  (printed in `fix-trials.log` as `[88,0,0,0,0,0]`) is an artifact of the pre-patch analyzer
  mis-scoring 5 of 6 corrupted, zero-stable-capture bursts as "0 disagreeing" instead of VOID; the
  VOID-aware re-analysis correctly reads all 6 VOID, 0 usable fw frames. T1, T2 and T3 were then
  rerun from a clean on-device capture, writing straight to disk instead of tmpfs
  (`orchestrate-trials-rerun.sh`, `fix-trials-rerun.log`): T1 all 0 / fw 0, T2 all 0 / fw 1, T3
  (`-UnifyDamagedRegions`) `[29, 15, 72, 35, 6, 27]` / fw 104 — the T3 number this README reports.
  B1 lost 4 of its 6 bursts to the same tmpfs exhaustion (`[VOID, VOID, VOID, VOID, 25, 25]`, fw
  38) and was not rerun. B0, T4 (all three flags combined), T5 (`-UseSkiaForComposition`) and B2
  came back complete: B0 `[33, 77, 50, 0, 24, 16]` fw 631; T4 `[0, 1, 0, 0, 0, 0]` fw 1; T5
  `[46, 0, 25, 15, 43, 60]` fw 182; B2 `[16, 25, 61, 28, 25, 0]` fw 24. Across every baseline and
  every trial but T1 (and T4, which combines T1's flag with the other two), both instruments show
  the same stale-content signature at a similar order of magnitude; T1 alone drives both to zero
  on every complete capture, isolating `-UseDamagingInformationForCompositing` as the trial that
  removes the defect.
- **Raw capture:** retained off-tree.

### Runs 63–66 — S4, isolating and shipping the fix, bench

- **Board:** bench, Pi Zero W. **Image commit:** `138d9142b2cff9c59cd0a755595bc3a82db7e3e3`
  (Runs 63–65) and `d97d6fe9b892321f76b333d0e9ad79a31edbd142` (Run 66).
- **Procedure:** Runs 63–64 were meant to run `kiosk-render-check.sh` live against `138d914`
  default and against `138d914` with T1's flag forced on by hand, as a live rehearsal of the
  render-check-stale detector built in Runs 67–68, ahead of the real fix; both aborted immediately
  on `burst/orchestrate-render-check.sh: line 37: label: unbound variable` (a `local label=$1`
  under `set -u` with no positional argument), before any series ran — no data either way. Run 65
  then attempted the OTA to `5ec7f0e` that Run 50 also needed; the install reached 72 %
  ("Copying image to rootfs.1") before the connection reset, `OTA_EXIT=255`; the device rebooted
  itself, came back on the untouched active slot (`138d914`, rootfs.0/A) with its retry budget for
  the inactive slot zeroed (`BOOT_B_LEFT=0`), and its buildinfo confirmed unmoved — a clean
  fallback, no data lost beyond the attempt itself. Run 66 is the fix: `kiosk-launch` now always
  passes `--features=-UseDamagingInformationForCompositing`, appending `KIOSK_COG_FEATURES` after
  a comma in the same argument when set (last value wins), landed as commit
  `d97d6fe9b892321f76b333d0e9ad79a31edbd142`; nothing in `kiosk-launch` scopes it to 2.54 by
  WPE version — "2.54 only" describes where it was developed and verified, not a guard in the
  code. The OTA to `d97d6fe` is confirmed by its own buildinfo match and by reading cog's argv
  back over the journal: `cog -P drm --features=-UseDamagingInformationForCompositing
  http://localhost:8080`, with no `KIOSK_COG_FEATURES` set.
- **Raw capture:** retained off-tree.

### Runs 67–72 — S4, the render-check STALE detector, bench

- **Board:** bench, Pi Zero W (Runs 67–68 are offline, over stored bursts; no board access).
  **Image commit:** `d97d6fe9b892321f76b333d0e9ad79a31edbd142` (Runs 69–71) and an attempted OTA
  to `5ec7f0e5bac8660bf407fd68bd1b96b7df6daba1` (Run 72).
- **Scripts deployed:** `tools/kiosk-render-check-stale.py` via `tools/kiosk-render-check.sh`
  (rc 0 clean, rc 2 could-not-tell, rc 3 STALE), validated offline by `validate-render-check-stale.py`
  against the bursts already captured in Runs 52–62; `kiosk-render-check-stale-test.py` (18/18)
  covers the eligibility change itself. Commit `646c513e0ff619d5e22f171b4c47e9084105e45a` relaxes
  eligibility from "both compared fbs need >= 2 stable captures" to "only one side needs 2, the
  other may hold exactly 1"; `run-v3-short.sh` takes one independent v3-style burst.
- **Procedure:** Run 67, offline, pre-fix: zero false positives on every known-clean burst; three
  known-stale-or-ambiguous bursts read rc 2 (could-not-tell), of which one is a genuine miss — a
  stale fb captured as a single stable frame, which the old eligibility rule could not compare at
  all. Run 68, the same offline sweep after `646c513`: every known-clean burst now reads rc 0 (0
  false positives), the genuine miss now reads rc 3 (stale_tiles=24, matching the v3 tile count
  for that same burst), and the other two could-not-tell results resolve to rc 0; four bursts that
  were already VOID for having 0 usable frames stay VOID, a data gap the classifier cannot fix.
  Run 69 is five live `kiosk-render-check.sh` passes against the fixed image at default: 165 of
  165 rc-bearing lines across the five runs (2 initial-frame + 30 series + 1 verdict, times 5) read
  0, no STALE verdict. Run 70 repeats this with `KIOSK_COG_FEATURES=UseDamagingInformationForCompositing`
  set — an attempt to re-enable, over the new default, the flag the fix just turned off — giving
  cog's argv `--features=-UseDamagingInformationForCompositing,UseDamagingInformationForCompositing`;
  five passes again all read 165/165 rc 0, and one independent v3-style burst taken under the same
  override reads 10 disagreeing tiles, well below the 16–77 per-burst range the same instrument
  reads on the `138d914` baseline trials (Runs 52, 56, 59; compare Run 44's 1–64 on `449e571`).
  The gap between the expected mostly-STALE
  result and the clean one actually seen is the entire basis for reading the override as having
  most likely failed to re-enable the feature — an inference from the size and verdict mismatch,
  not a direct confirmation; the comma-joined argv string was built exactly as intended. Run 71
  repeats both conditions once more (labelled V4b and V1b in the capture, a re-sequenced
  repeat ahead of the S4 smoothness/soak below, not a third condition): 165/165 rc 0 again, both
  ways. Run 72, queued under the same lock as Run 71, is the OTA to `5ec7f0e` for a live
  pre-fix-image comparison; its log ends after starting the install with no result line — not yet
  run as of this snapshot, so fact 8's "live test against the pre-fix image" stays open.
- **Raw capture:** retained off-tree.

### Runs 73–76 — S4 smoothness/soak, the fixed image, bench, commit `d97d6fe`

- **Board:** bench, Pi Zero W. **Image commit:** `d97d6fe9b892321f76b333d0e9ad79a31edbd142`,
  slot B, from each capture's own header; tonight, 3/4 park cards live (one closed for the night).
- **Scripts deployed:** each capture's own `# harness` line self-stamps
  `635af22c3b97af1bd9c4080f24dd730cf6500198`, but the files it produced do not match either
  outcome the version of `run-s4-smoothness.sh` committed at that pin, or at `HEAD`, can print.
  A locally edited, never-committed `run-s4-smoothness.sh`, found in a sibling worktree, takes a
  4th positional argument (`MIN_LIVE`, default 4) and relaxes the gate from `all_live` (`c=4 l=4`)
  to `all_at_least(lines, MIN_LIVE)` — a function of the same name added to that worktree's own,
  likewise uncommitted, `parse_cards_probe.py`; the orchestrator passed 3, for tonight's known
  3/4-card state. This README's own copies of both files (Harness, above) are the unmodified
  `all_live` versions; the scripts that actually ran tonight are not beside this README — a
  concrete instance of the R2 gap, not a one-off inline command this time but an edited,
  never-committed pair of scripts.
- **Procedure:** three back-to-back 585 s smoothness captures, cache cleared and kiosk restarted
  before each. Each capture's own cards-live gate reads VOID: its first `CP|` sample, at t=4 s,
  before the page has loaded (`c=0 l=0`), counts against the deployed "`l>=3` throughout" rule the
  same as a genuine drop would. A reclassification pass (`reclassify_cards_window.py`, likewise
  not committed here), recorded in each file as a separate, appended block, excludes samples
  before the 15 s settle window (`parse_smoothness.py`'s own `steady_from`) and reclassifies all
  three LIVE (`l>=3` throughout the judged window, 19 of 20 samples; `l` never reaches 4 — one
  park stays closed the whole capture). Both labels are recorded here: VOID as the deployed gate's
  own rule produced it, LIVE as the reclassification corrects for the load-time sample. Run 76 is
  the 1 h soak that follows: `run-s4-soak.sh` records cards-live as a fraction, by design, and
  never VOIDs a run on it (see the soak's own Harness entry above) — but the same reclassification
  script was run against it anyway, found `l` drop to 2 after a second park closes partway through
  (at t=330 s) and read VOID, which is a misapplication of the smoothness gate's rule to data it
  was never meant to gate; Run 76's result stands un-voided for stability, which is what it was
  designed to measure.
- **Raw capture:** retained off-tree. Parsed with `parse_smoothness.py` (Runs 73–75) and
  `parse_module_fault.py` (Run 76); see Metrics.

### Run 77 — V1-real, the live render-check-stale proof against the pre-fix image, bench, commit `138d914`

- **Board:** bench, Pi Zero W, temporarily OTA'd back to `138d914` for this run and returned to
  `d97d6fe` afterward (confirmed by the post-run buildinfo check); after park hours, 2/4 cards
  live. **Image commit:** `138d9142b2cff9c59cd0a755595bc3a82db7e3e3`.
- **Scripts deployed:** `tools/kiosk-render-check.sh` ×5 and `run-v3-short.sh` ×1, as Runs 69–71;
  the orchestration (`orchestrate-v1-real.sh`) was not saved — an R2 gap, as for the other
  orchestrators in Runs 63–72.
- **Procedure:** this is Runs 63–64's rehearsal, finally run against the real pre-fix condition —
  `138d914` at default, no flag override — rather than crashing on the unbound-variable bug.
  Five render-check passes all read rc 0, stale tiles=0; the one independent v3-style burst also
  reads 0 disagreeing tiles, though `testable_tiles=0` for that burst (the two fb ids never
  co-occurred as stable captures in it, the same vacuous-zero case as Run 46's burst 8, not a
  tested-and-clean result). The fault is absent here, not missed by the detector: Runs 67–68
  confirm the detector reads real disagreement correctly on stored data, and this run's own
  detector mechanics are identical to Runs 69–71's. What differs from the afternoon's B0/B1/B2
  baselines on this same image (Runs 52, 56, 59: 16–77 disagreeing tiles per burst, in nearly
  every burst) is park hours: this run is after hours with 2/4 cards live, against whatever state
  the page was in during the afternoon's trials. Whether live card content is what triggers the
  defect is unmeasured by this run alone — it is recorded here as an open hypothesis, not a
  finding, and #198 (STALE check live proof) is where it is meant to be tested against a
  controlled page state.
- **Raw capture:** retained off-tree.

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
- `run-soak.sh` — the 1 h soak: the same pre-run screenshot settle as `run-smoothness.sh`, which
  also gives cog time to recreate a cache that a preceding run's restore cleared, then
  `mf-probe.js` as `KIOSK_PROBE` user script, its `MF|` samples read from the kiosk journal, then
  the `kiosk-soak` samples and summary, restarts, boot ids, swap counters, PSI and kernel OOM lines
  for the window. `mf-reader.sh` read the title over X for the baseline soak.
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
- `cog-cache.sh` — sourced by the three drivers: resolves cog's cache on the board as WebKit's
  network-session default, `<XDG_CACHE_HOME, else HOME/.cache, of the running cog, else uid 0's
  passwd home/.cache>/wpe` (`/home/root/.cache/wpe` on bench), and clears it, each clear logging
  `# cleared <dir> (<n> entries)` or `# no cache dir found (<dir>)`. Before deploying anything,
  `run-smoothness.sh` and `run-soak.sh` check that dir and exit 3, VOID, if it is absent or holds
  no entries, so every capture's first clear empties a populated cache.
  `check-cog-cache-resolver.sh` prints the resolved dir and its entry count and deletes nothing.
- `analyze_burst.py`, `analyze_burst2.py` — S4's first stale-content instrument: per named region
  (hand-picked crop, or `analyze_burst2.py`'s fixed render-check crop), a content hash per frame
  and a "revert" where a hash repeats at distance > 1 with no repeat at distance 1 (A,B,A, not
  simple steadiness). `cross_match.py` and `full_cross_match.py` extend it to full provenance and
  cross-run exact matching, on the crop and the whole 1280x720 frame. Rejected (Runs 42–43):
  this page's content changes continuously, so a whole-crop exact hash never repeats regardless
  of rendering mode.
- `kiosk-drmgrab --report` / `analyze_burst_v2.py` — the DRM scanout fb id read before and after
  each PPM copy, plus the copy's wall time; a capture is unstable when the two ids differ. The
  mechanism Runs 44–72 build on.
- `analyze_burst_v3.py` / `run-burst-capture-v3.sh`, `run-burst-capture-v3-control.sh`,
  `run-v3-short.sh` — the per-tile instrument: a burst's STABLE captures only, grouped by scanned
  fb id, tiled 40x40 px (32x18, 576 tiles); a tile "disagrees" where the two fb groups differ
  (mean abs pixel diff > 1), is a "late-change artifact" where one legitimate mid-burst content
  change fully explains it, and is "persistent" where it disagrees in >= 2 consecutive bursts.
  `run-v3-short.sh` takes a parameterized number of bursts for a short, targeted check.
- `kiosk-fwgrab` / `sanity-fwgrab.sh`, `run-fw-burst-capture.sh`, `analyze_fw_burst.py` — a
  VideoCore dispmanx framebuffer snapshot, independent of the DRM scanout path and of
  `kiosk-drmgrab`; no fb id, timed externally. The same 40x40 px tiling with a "flip" rule (a
  tile A,B,A across three consecutive frames) in place of the fb-grouped disagreement test, since
  dispmanx carries no fb id to group by.
- `run-load-experiment.sh` — three fixed CPU-contention phases (idle, a CSS spinner, a tight DRM
  read loop) run back to back, each captured and tiled as a `kiosk-fwgrab` burst, to test whether
  flip rate tracks CPU load.
- `run-feature-trial.sh` — one `KIOSK_COG_FEATURES` trial: deploys the value (or none, for a
  baseline), six 15-frame `analyze_burst_v3.py` bursts and one 90-frame `analyze_fw_burst.py`
  burst, each parsed fail-closed — a burst that cannot be parsed VOIDs that burst alone, never
  silently reads as zero.
- `tools/kiosk-render-check-stale.py`, via `tools/kiosk-render-check.sh` — the STALE verdict
  (rc 3) added to render-check's existing clean/could-not-tell (rc 0/rc 2): a 30-frame series,
  batched 5, scored by the same fb-grouped tile-disagreement rule. Eligibility (which fb pairs are
  compared) was relaxed in `646c513e0ff619d5e22f171b4c47e9084105e45a` from requiring both
  compared fbs to hold >= 2 stable captures to requiring only one side to; covered by
  `kiosk-render-check-stale-test.py` (18/18). `validate-render-check-stale.py` reruns the
  classifier offline over already-captured bursts, with no new device access.
- `cards-probe.js` / `parse_cards_probe.py` — the mechanical page-state gate (committed
  `48f3bfd68a1d429f5d5c438ed5fcc1c96c95cc2b`): every 30 s, and once on load, it logs
  `CP|t=<sec>|c=<n>|l=<n>`, where `c` is the count of `[data-pwt-card]` elements and `l` the
  subset of those that also contain `[data-pwt-leaderboard]` (live data, as opposed to a closed
  or API-failed card, neither distinguished from the other by this probe). `all_live` requires
  every parsed sample to read `c=4 l=4`; `live_fraction` reports the `l=4` fraction instead, for
  a soak that may legitimately cross a park-hours boundary. Replaces judging "cards live" by eye
  from the pre-run screenshot (Runs 2–41's limitation); first used operationally against image
  `d97d6fe9b892321f76b333d0e9ad79a31edbd142`, in `run-s4-smoothness.sh` and `run-s4-soak.sh`.

**Redacted harness scripts.** The S4 scripts are committed as run except one redaction: the bench
ssh target is read from `$BENCH` (`${BENCH:?ssh target…}`) where the script held a literal
address, in `compensate-v1p.sh`, `compensate-v3.sh`, `orchestrate-244-load.sh`,
`orchestrate-244.sh`, `orchestrate-254-load.sh`, `orchestrate-d97d6fe-v4.sh`, `orchestrate-fw.sh`,
`orchestrate-live-proof.sh`, `orchestrate-load254-and-trials.sh`, `orchestrate-render-check.sh`,
`orchestrate-s4-only.sh`, `orchestrate-s4-smoothness-soak.sh`, `orchestrate-trials-rerun.sh`,
`orchestrate-trials.sh`, `orchestrate-v2.sh`, `orchestrate-v3-retry.sh`, `orchestrate-v3.sh`,
`ota-verify-138d914.sh`, `ota-verify-449e571.sh`, `ota-verify-5ec7f0e.sh` and
`ota-verify-d97d6fe.sh`.

**Aborting a driver:** kill its process group, `kill -TERM -- -<pgid>`. Bench runs launch
drivers with `setsid nohup …`, so each has its own group; `ps -o pgid= -p <driver pid>` prints
it. Killing the group also ends the foreground ssh or sleep, so the EXIT trap restores
`kiosk.conf` at once. A TERM to the driver alone is held until that child returns. In
`run-time-to-page.sh`, an abort while the board is rebooting runs the restore against a board
that is down. The restore fails, and the `kiosk.conf.wpe-bak` or `kiosk.conf.wpe-absent` backup
stays in `/data/config/`. The next run then refuses until that backup is restored by hand.

**S4 process notes.** A host `/tmp` tmpfs filled during the trials chain (Runs 52–62), corrupting
Run 55 (T3) outright and part of Run 54 (T2)'s fw transfer; the affected trials were rerun to
disk instead (Runs 60–62). An unbound-variable bug (`local label=$1` under `set -u`, no
positional argument) voided Runs 63–64 before any render-check series ran, and Run 64's abort did
not fire its restore trap: an operator check found `KIOSK_COG_FEATURES=-UseDamagingInformationForCompositing`
still in `/data/config/kiosk.conf` while Run 65's OTA to 2.44.4 was installing, before the
reboot; it was restored from `kiosk.conf.v2-orig` and `cmp`-verified identical, so 2.44.4 never
booted carrying a feature flag it may not recognize. Separately, two already-running orchestrator
processes still held the pre-fix script in memory when the fix landed (one driving Run 65's OTA
step, the other the live-proof chain in Runs 69–71), so `compensate-v1p.sh` and `compensate-v3.sh`
were run to check each for a second, independent dirty-`kiosk.conf` risk from its own in-flight
condition: `compensate-v1p.sh` found it clean, `compensate-v3.sh` refused to compensate because
the board's buildinfo did not yet match the image it was meant to check. Run 65's OTA itself
failed cleanly: a network reset at 72 % install, a self-reboot, and a return to the untouched
active slot with its retry budget zeroed. Every orchestrator is designed to write its own
`.log.done` marker last, in an exit trap, so a waiter blocks on that file rather than an outer
wrapper that may not exist; four instances of this stalling a waiter, or never resolving at all,
are confirmed by the `.log`/`.log.done` timestamps: `build-138d914.log` completed
(`BUILD_EXIT=0`) at 14:33:46, but `orchestrate-fw.sh` (`--- waiting for build-138d914.log.done
---`) blocked until 14:43:48, a 10-minute stall; `build-5ec7f0e.log` completed at 14:37:21, and
`orchestrate-244.sh` (`--- waiting for build-5ec7f0e.log.done ---`) blocked on the same marker
until 14:43:48, a 6-minute stall; `orchestrate-fw.log` printed `ORCHESTRATE_FW_DONE` at 14:58:48,
and the same `orchestrate-244.sh` (`--- waiting for orchestrate-fw.log.done (fw chain must
release the lock first) ---`) blocked until 15:13:58, a 15-minute stall. `orchestrate-v3.sh`
(which launched Runs 44–45's capture) printed its own completion line at 14:20:54 and never wrote
a `.log.done` at all; no later orchestrator in these logs is seen naming it as a wait, so unlike
the other three this one is not confirmed to have stalled anything downstream.

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

**Run 31** (`s3-rerun-smoothness-run1.txt`)

| sec | frames | mean fps | % <50 ms | max ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|---|
| 581 | 29469 | 50.72 | 98.8 | 1638 | 53 | 0.0795/s (45 from ref_t 13 s) | 11 |

**Run 32** (`s3-rerun-smoothness-run2.txt`)

| sec | frames | mean fps | % <50 ms | max ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|---|
| 580 | 30643 | 52.83 | 99.1 | 1548 | 47 | 0.0673/s (38 from ref_t 14 s) | 8 |

**Run 33** (`s3-rerun-smoothness-run3.txt`)

| sec | frames | mean fps | % <50 ms | max ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|---|
| 581 | 32473 | 55.89 | 99.5 | 1547 | 8 | 0.0035/s (2 from ref_t 14 s) | 5 |

**Run 34** (`s3-rerun-soak.txt`; MF| from `parse_module_fault.py`, 121 samples)

| fmax | fever | umax | restarts | reboots | OOM lines | min MemAvailable | rss_total | swap in/out | PSI |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | 237 MB | 166596 → 212696 kB, slope +50139 kB/h (n=12) | 0 / 0 | unavailable |

**Run 14** (`s2-paintgate.txt`)

| render-check | screenshot mean | gpu-check | processes on `/dev/dri` |
|---|---|---|---|
| rc 0, advancing | 13.79 | rc 0 | cog (4 fds), WPEWebProcess (7 fds), both `vc4_dri.so`; WPENetworkProcess none |

**Run 20** (`s2-vc4-hwevidence.txt`)

| V3D BOs | V3D shader BOs | binner | dumb | WPEWebProcess maps |
|---|---|---|---|---|
| 14728 kB (11) | 12 kB (3) | 16384 kB (1) | 4052 kB (1) | `vc4_dri.so`; 7 `renderD128` mappings |

**Run 35** (`s4-smoothness-run1.txt`)

| sec | frames | mean fps | % <50 ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|
| 583 | 28248 | 48.45 | 97.9 | 24 | bounded 0.0246–0.0423/s (14–24) | 11 |

**Run 36** (`s4-smoothness-run2.txt`)

| sec | frames | mean fps | % <50 ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|
| 580 | 28314 | 48.82 | 98.4 | 27 | bounded 0.0248–0.0478/s (14–27) | 11 |

**Run 37** (`s4-smoothness-run3.txt`)

| sec | frames | mean fps | % <50 ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|
| 580 | 28251 | 48.71 | 98.3 | 28 | bounded 0.0248–0.0496/s (14–28) | 12 |

**Run 40** (`s4-skia-cpu-run1.txt`)

| sec | frames | mean fps | % <50 ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|
| 581 | 26501 | 45.61 | 96.7 | 153 | bounded 0.0247–0.2703/s (14–153) | 13 |

**Run 73** (`s4-smoothness-run1.txt`)

| sec | frames | mean fps | % <50 ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|
| 580 | 29552 | 50.95 | 98.4 | 26 | bounded 0.0248–0.0460/s (14–26) | 13 |

**Run 74** (`s4-smoothness-run2.txt`)

| sec | frames | mean fps | % <50 ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|
| 581 | 29737 | 51.18 | 98.3 | 26 | bounded 0.0247–0.0459/s (14–26) | 13 |

**Run 75** (`s4-smoothness-run3.txt`)

| sec | frames | mean fps | % <50 ms | bt | stall rate t ≥ 15 s | clusters |
|---|---|---|---|---|---|---|
| 580 | 29551 | 50.95 | 98.3 | 25 | bounded 0.0248–0.0442/s (14–25) | 12 |

**Run 76** (`s4-soak.txt`; MF| from `parse_module_fault.py`, 121 samples)

| fmax | fever | umax | restarts | reboots | OOM lines | min MemAvailable | rss_total | swap in/out | PSI |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 1 | 0 | 0 | 0 | 301 MB | 182080 → 185844 kB, slope +4097.5 kB/h (n=12) | 0 / 0 | unavailable |

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
- **With a populated cache cleared before every run (Runs 31–33), the stall trains still come and
  go.** Run 31 carries the ~40 s train of ~360 ms stalls from 42 s to the end and a sparse 8 s
  train; Run 32 carries both trains from the start, with bursts near 250 s and 305 s, then almost
  none; Run 33 carries neither (2 steady stalls). The full timelines are the union of each
  capture's `MP|` big[] lists, which holds every stall (its size equals bt).
- **No log line coincides with the stall trains** (Run 28): in the first 90 s after each of Runs
  24–26's restarts the backend logged nothing, and the kiosk journal holds the start-up lines and
  the probe's titles only.
- **The WPE soak (Run 34) is clean:** no module fault in 121 samples, no restart, no reboot, no OOM
  line, no swap. Memory is recorded, not judged: rss_total 166596 → 212696 kB, slope
  +50139 kB/h (n=12), min MemAvailable 237 MB.
- **Time to page on WPE: 43.36, 40.78, 43.28 s** (Run 22), recorded, not judged, against the X
  baseline's 48.00, 59.63, 50.80 s (Run 13). Every boot's timesyncd sync (55.6–66.3 s monotonic)
  came after the beacon, so all three are in the beacon's pre-step frame.
- **S4: the panel shows stale content under default 2.54 rendering, not only under
  `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1`.** Run 41's visible flashing was first attributed to CPU
  rendering; Runs 44–45's v3 tile analysis RETRACTS that attribution — the default-rendering
  control burst disagrees on as many tiles, in the same screen regions, as the CPU-rendering
  phase, on the same image. Run 46 finds zero disagreement under the same instrument on 2.44.4,
  which is the first evidence the defect is specific to 2.54, not to any rendering mode.
  `-AcceleratedCompositing` (Run 39) is not a workaround: it crash-loops the renderer outright.
- **Two whole-crop exact-hash revert instruments find nothing** (Runs 42–43): a continuously
  changing page never repeats a crop's hash closely enough for an A,B,A revert rule, on this
  image, in either rendering mode; rejected as a detector.
- **`kiosk-drmgrab --report` shows the scanout alternating between two framebuffers** (Run 43):
  ids 96 and 98 throughout, the before/after id differing in roughly a fifth of captures
  (14/60 control, 23/120 cpu), copy time ~173 ms median — the mechanism the tile analysis and the
  render-check STALE detector are built on.
- **The stale content is a per-tile disagreement between the two scanout framebuffers, not a
  uniform frozen frame.** Runs 44–46: 1–64 tiles disagree per burst on default 2.54, with a
  persistent ~50-tile core in a few fixed screen regions across 12 bursts; the same instrument
  reads 0 on 2.44.4.
- **`kiosk-fwgrab` (dispmanx) cross-validates against `kiosk-drmgrab`** (Run 48: matching mean
  luma and content) and finds the same flip behaviour independent of the DRM scanout path
  (Run 49: 0 flips on one 90-frame burst; Run 51: 284/64, 120/24 and 6/0 flips/tiles≥3 across
  idle, spinner and a tight DRM read loop) — flips occur at rest as well as under load, which
  does not support a CPU-load cause. The CPU-contention experiment's 2.44.4 arm is VOID (Run 50):
  `kiosk-fwgrab` does not exist on that image.
- **2.54's page fill is slow but fault-free** (Run 47): the pre-run screenshot's mean luma
  oscillated 5.47–7.73, below the settle threshold, for the first ~4 minutes after boot on image
  `138d914`, reaching 16.43 by roughly 16 minutes; the kiosk journal for that boot logs no error
  or crash.
- **`-UseDamagingInformationForCompositing` isolates the defect** (Runs 52–62): across three
  clean baselines (B0, B1's 2 complete bursts, B2) and four other single- or combined-flag
  trials, both the tile and the fw-flip instrument read a similar stale-content signature;
  turning this one flag off, alone or combined with the other two (T4), drives both instruments
  to zero on every run with complete data. A host tmpfs filling mid-chain corrupted T2's fw
  capture and T3's capture outright (RETRACTED: T3's original `[88,0,0,0,0,0]` series is a
  pre-patch analyzer artifact on corrupted frames, not a real zero result); T1–T3 were rerun
  clean to disk.
- **The fix:** `kiosk-launch` passes `--features=-UseDamagingInformationForCompositing` by
  default on every boot (`d97d6fe9b892321f76b333d0e9ad79a31edbd142`), `KIOSK_COG_FEATURES`
  appended after a comma in the same argument when set. Nothing in the code scopes this to 2.54;
  it is unconditional, developed and verified against this image.
- **The render-check STALE detector (rc 3) is clean offline and live on the fixed image, with
  one eligibility gap closed.** Offline, zero false positives on known-clean bursts both before
  and after `646c513e0ff619d5e22f171b4c47e9084105e45a`; the one genuine miss it closes is a stale
  framebuffer captured as a single stable frame, outside the old eligibility rule entirely. Live
  on `d97d6fe`, five render-check passes at default and five with
  `KIOSK_COG_FEATURES=UseDamagingInformationForCompositing` both read 165/165 rc lines 0 — the
  override's one independent v3-style burst (10 disagreeing tiles, against 16–77 per burst on
  default) suggests it most likely did not re-enable the feature, an inference from the size
  mismatch rather than a direct confirmation. A live render-check pass against the pre-fix image
  itself has not yet completed (two attempts at the OTA to 2.44.4 for the comparison point, one
  failed on a network reset, one not yet run), so that comparison stays open.
- **S4 process incidents, recorded as process notes, not findings about the defect:** a tmpfs
  fill (above); two orchestrators crashing on an unbound variable before producing any
  render-check data, one of which left `kiosk.conf` dirty with a feature flag until an operator
  check caught and restored it mid-OTA; three `.log.done` markers written 6, 10 and 15 minutes
  late, each stalling a named downstream orchestrator for that long, and one (`orchestrate-v3.sh`)
  never written at all, with no confirmed downstream stall; and one OTA (to 2.44.4) that failed
  cleanly on a network reset and fell back to the active slot untouched.
- **Page state was judged by eye through Run 41** (mean luma of the pre-run screenshot, same as
  S1–S3); the mechanical `cards-probe.js` gate (`c=4 l=4` on every sample) was committed
  (`48f3bfd68a1d429f5d5c438ed5fcc1c96c95cc2b`) afterward (Runs 73–76 above); the scripts that
  actually ran Runs 73–76 relax it to `l >= MIN_LIVE` and are not the ones committed here.
- **The fixed image passes smoothness and is stable** (Runs 73–76): 50.95–51.18 fps,
  98.3–98.4 % <50 ms, against a 3/4-card page (one park closed for the night); the cards-live
  gate VOIDs each of the three smoothness captures on their first, pre-load sample alone, and a
  reclassification over the measured window alone reads all three LIVE. The 1 h soak is clean —
  0 restarts, 0 reboots, no OOM, no swap, `fmax`/`fever` 0 in all 121 samples — regardless of a
  second park closing and `l` dropping to 2 partway through; the soak was designed to record
  cards-live as a fraction, never to VOID on it, and a reclassification script's VOID verdict
  against it is a misapplication of the smoothness rule, not a real stability finding.
- **The pre-fix defect was absent, not missed, in a live render-check pass against `138d914`
  after park hours** (Run 77: 5/5 rc 0, stale tiles=0, matching the same detector's clean reads
  on `d97d6fe` in Runs 69–71). The afternoon's baselines on this same pre-fix image showed the
  defect in nearly every burst (Runs 52, 56, 59). Whether live card content is what the defect
  needs to show is an open hypothesis from this contrast, not a measured finding — #198 STALE
  check live proof is where it is meant to be tested against a controlled page state.

## Verdict

- **Smoothness, against the X baseline (S1):** GO. E1's `regression_reasons` finds no regression
  on any metric between the fixed image's smoothness (Runs 73–75) and the X baseline (Runs 2–4).
- **Smoothness, against pre-fix 2.54 (`f4d4bb8`, Runs 35–37):** GO — turning the damage feature
  off costs nothing. Mean fps rises from 48.45–48.82 to 50.95–51.18, roughly +2.5 fps run for run.
- **Smoothness, against 2.44.4 (S3, Runs 24–26):** NO-GO under the literal rule. The fixed
  image's worst `% frames <50 ms` is 98.28432201955941, against 2.44.4's best-case floor of
  98.3 (Run 25) — a 0.016 percentage-point miss. Both sides of this comparison are read on a
  3/4-card page (one park closed for the night on the candidate side; see the X/2.44.4 runs'
  own page-state notes), so the margin is this close on a page state neither baseline measured
  directly against the fixed image's own tonight.
- **Stability:** GO. Runs 69–76 and Run 34 together show zero module faults, zero restarts,
  zero reboots and no OOM line on either image under test.
- **Module faults:** none, on any S4 run that completed (Runs 69–76).
- **The cutover is wpewebkit 2.54**, with `kiosk-launch` passing
  `--features=-UseDamagingInformationForCompositing` by default
  (`d97d6fe9b892321f76b333d0e9ad79a31edbd142`).

## Changes configured as a result

**Code change**, shipped ahead of this verdict: `kiosk-launch` passes
`--features=-UseDamagingInformationForCompositing` by default on every boot
(`d97d6fe9b892321f76b333d0e9ad79a31edbd142`), closing the stale-content defect this investigation
traced to that WPE feature. The cutover to WPE WebKit 2.54 + cog stands on that fix.

Follow-ups opened by this investigation, each its own ticket:
- #190 upstream damage-feature report
- #191 own WPE launcher
- #192 2.54 page fill delay
- #193 cog shutdown crash
- #194 DOM card-count gate
- #195 pipeline rollback gap
- #196 WPE build-time levers
- #197 kiosk-bootprof WPE port
- #198 STALE check live proof
