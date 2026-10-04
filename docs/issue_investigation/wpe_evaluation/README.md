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
- **Candidate (WPE):** the `#185 W1` commits on `185-wpe-evaluation`; recorded per run once built.

## Harness

All one-off and committed beside this README (R2), except where a run names a shipped tool.

- [`p7_min.js`](../gpu_compositing/p7_min.js) — smoothness probe, used unmodified from the
  gpu_compositing investigation.
- `mf-probe.js` — module-fault probe: every 30 s it writes the `MF|` payload to `document.title`.
- `parse_smoothness.py`, `parse_module_fault.py` — payload parsers, each proven by its `_test.py`
  on synthetic payloads.
- `verdict.py` — the go/no-go over the parsed runs, proven by `verdict_test.py`.
- `run-smoothness.sh` — one smoothness capture: pre-run screenshot into `local/`, then
  [`run-appliance.sh`](../gpu_compositing/run-appliance.sh) unchanged (`p7_min.js`, 585 s).
- `run-soak.sh`, `mf-reader.sh` — the 1 h soak: `mf-probe.js` deployed, its title read on the board
  every 30 s, then the `kiosk-soak` summary, restarts, boot ids and kernel OOM lines for the window.
- `run-time-to-page.sh` — three cold boots, one connection each at 120 s, shipped `measure-surf.sh`.
- `xval-capture.sh`, `xval-judge.sh` — `kiosk-drmgrab` cross-validated against
  `import -window root`: two capture pairs 61 s apart, judged on a static crop (AE = 0, crop rich
  enough to expose a de-tile or channel-order bug) and a clock crop (must change).

## Metrics

Per run, one table per run. None yet.

## Findings

None yet.

## Changes configured as a result

Pending the verdict.
