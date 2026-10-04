# What does a cold-cache full build cost, and how far do the icon-theme, WebKit-debug and WebKit-parallelism levers cut it?

| | |
|---|---|
| **Issue** | #176 WebKit build time |
| **Status** | open |
| **Opened / concluded** | 2026-10-03 / |

A cold full image build on the build host (4c/8t, WSL2 capped at 12 GB, 11 GB as the tree sees it,
16 GB swap) has taken 6h51m-9h44m across three prior buildstats runs (`20260828163401`,
`20260930184746`, `20261002222637`), all at the WebKit `PARALLEL_MAKE` of `-j2`. In every one,
`webkitgtk3:do_compile` runs alone for 260 min with 6 of 8 threads idle, and the rest of the build
spends ~3.5 h on 6 bitbake slots with `rust-llvm-native:do_compile` (11471 s) as its longest chain --
present only because `gtk+3` RRECOMMENDS `adwaita-icon-theme-symbolic`, which pulls in `librsvg` and
a Rust toolchain build nothing else in this image needs. This investigation measures one cold build
with the three agreed levers applied together (owner rulings, 2026-10-03): the icon theme dropped,
WebKit built without debug info, and WebKit's `PARALLEL_MAKE` raised to `-j6` on the strength of a
prior `-j6` build that completed on this host. The restart rule and its figures are not yet run; this
section is filled in once the run (or its restart) completes.

## Test runs

| Run | Board (role) | Image commit | Harness / scripts | Result (1 line) |
|---|---|---|---|---|
| 1 | none -- build host, `MACHINE=raspberrypi0-wifi` | `<sha, filled after the run>` | `run-cold-build.sh`, `watch.sh`, `collect.sh`, `parse_buildstats.py` -- all one-off, committed here | *pending* |

If a restart fires, the restarted attempt is Run 2 and gets its own row and its own `### Run 2`
section below; the two are never merged into one table (R3).

### Run 1 -- build host, commit `<pending>`

- **Board:** none. This run is a build, not a device test. The build host is 4c/8t, 11 GB, 16 GB
  swap; the image is built for `MACHINE=raspberrypi0-wifi`.
- **Image commit:** *filled after the run* -- `git rev-parse HEAD` as recorded in
  `build/coldbuild/host-start.txt` at launch, confirmed by
  `tools/write-build-rev.sh`'s `KIOSK_BUILDINFO_REV`.
- **Scripts deployed, each ONE-OFF, committed beside this README:**
  - `write-overlay.sh` -- writes the `TMPDIR`/`SSTATE_DIR`/`BUILDHISTORY_DIR` overlay.
  - `proofs.sh` -- the three pre-run proofs (a)-(c), output under `proofs/`.
  - `run-cold-build.sh` -- launches the build and `watch.sh`, detached.
  - `watch.sh` -- 60 s memory/progress samples and the restart triggers, in `watch.log`.
  - `restart-webkit.sh` -- the restart rule's stop/cleansstate/resume, if a trigger fires.
  - `collect.sh` -- packs the evidence below after the run.
  - `parse_buildstats.py` -- the two reporting figures, checked against the known prior run
    `20261002222637` (9h44m49s wall, 21960 s WebKit `do_compile`) before being trusted here.
- **Procedure:** `just pipeline-off` once idle; `proofs.sh`; `run-cold-build.sh`, which refuses unless
  the pipeline is idle, records host state, writes the overlay, and launches
  `tools/kas-run.sh build kiosk-zero-w.yaml:build/coldbuild/zz-coldbuild.yaml` against an empty
  `build/coldbuild/{tmp,sstate-cache,buildhistory}`. `watch.sh` runs alongside it. On a restart
  trigger, the next `-j` step is committed and `restart-webkit.sh <j>` applied; otherwise the build
  runs to completion. `collect.sh` afterward, then `just pipeline-on`.
- **Raw capture:** *filled after the run* -- `buildstats-<runid>.tar.xz`,
  `parse-report-<runid>.md`, `webkit-compile-line-<runid>.txt`, `manifest-packages-<runid>.txt`,
  `local-conf-dirs-<runid>.txt`, and `proofs/{a,b,c}-*.txt`.

## Configuration under test

The tree facts this run rests on:

- **Icon theme dropped.** `kiosk-zero-w.yaml`'s `trim:` block adds
  `RRECOMMENDS:gtk+3:remove = "adwaita-icon-theme-symbolic"`, which takes `adwaita-icon-theme`,
  `hicolor-icon-theme`, `librsvg`, `librsvg-native`, `rust-native`, `rust-llvm-native` and
  `cargo-native` out of the build graph and the image. WebKit's own broken-image and form-control
  icons are compiled into WebCore, so nothing in the running kiosk depends on the removed theme.
- **WebKit built without debug info.** The `parallel:` block adds
  `DEBUG_FLAGS:remove:pn-webkitgtk3 = "-g -g1"`, on top of the recipe's own `-g1` (already in place
  before this ticket). `DEBUG_PREFIX_MAP`'s tokens are untouched, so the webkit `-dbg` packages become
  near-empty rather than disappearing, and nothing in this tree uses them.
- **WebKit's `PARALLEL_MAKE` raised to `-j6`.** Same `parallel:` block,
  `PARALLEL_MAKE:pn-webkitgtk3 = "-j6"`, matching the global `PARALLEL_MAKE` for the first time.
  `BB_NUMBER_THREADS`, the global `PARALLEL_MAKE`, `BB_PRESSURE_MAX_MEMORY` and every other recipe are
  untouched. `PARALLEL_MAKE` is in bitbake's own `BB_HASHEXCLUDE_COMMON` by default (poky's
  `bitbake.conf`), which is proof (c) -- the `-j` change cannot bust sstate hash equivalence.
- **"Cold" is an empty `TMPDIR`/`SSTATE_DIR`/`BUILDHISTORY_DIR`**, under `build/coldbuild/` via the
  generated `zz-coldbuild` `local_conf_header` block (sorts last by name, following
  `tools/rauc-rotate-build.sh`'s `${TOPDIR}` overlay precedent). `DL_DIR` and the pipeline's shared
  `build/sstate-cache` are untouched -- a download is not a build cost, and this investigation never
  writes the pipeline's own sstate.
- **GTK/WPE is out of scope here**, split to #185.

## Metrics

*Filled after the run.* One table per run (R3); `parse-report-<runid>.md` is the source.

## Findings

*Filled after the run.*

## Changes configured as a result

*Filled after the run* -- the code change is already in this branch (`kiosk-zero-w.yaml`); this
section records what the run showed once it has run, and whether the restart rule fired.
