# What does a cold-cache full build cost, and how far do the icon-theme, WebKit-debug and WebKit-parallelism levers cut it?

| | |
|---|---|
| **Issue** | #176 WebKit build time |
| **Status** | concluded → code change |
| **Opened / concluded** | 2026-10-03 / 2026-10-04 |

A cold full image build on the build host (4c/8t, WSL2 capped at 12 GB, 11 GB as the tree sees it,
16 GB swap) had taken 6h51m-9h44m across three prior buildstats runs (`20260828163401`,
`20260930184746`, `20261002222637`), all at the WebKit `PARALLEL_MAKE` of `-j2`. In every one,
`webkitgtk3:do_compile` ran alone for 260 min with 6 of 8 threads idle, and the rest of the build
spent ~3.5 h on 6 bitbake slots with `rust-llvm-native:do_compile` (11471 s) as its longest chain --
present only because `gtk+3` RRECOMMENDS `adwaita-icon-theme-symbolic`, which pulls in `librsvg` and
a Rust toolchain build nothing else in this image needs. This investigation measured one cold build
with the three agreed levers applied together (owner rulings, 2026-10-03): the icon theme dropped,
WebKit built without debug info, and WebKit's `PARALLEL_MAKE` raised to `-j6` on the strength of a
prior `-j6` build that completed on this host. **Result: cold full build ~6 h (was ~9h44m worst
case), WebKit-invalidating rebuild ~3 h.** No restart fired -- only active thrash or an OOM-kill
restarts the build, and neither happened.

## Test runs

| Run | Board (role) | Image commit | Harness / scripts | Result (1 line) |
|---|---|---|---|---|
| 1 | none -- build host, `MACHINE=raspberrypi0-wifi` | `cd1e85a3e7f563d5449eb5d80447bba39ab8177e` | `run-cold-build.sh`, `watch.sh`, `collect.sh`, `parse_buildstats.py`, `ninja-log-compare.py` -- all one-off, committed here | Cold full 5h46m37s, WebKit rebuild 3h13m01s; no restart (no thrash, no OOM) |

No restart fired (see [Findings](#findings)), so this is the only run; the three prior runs are
cited above and in Findings by buildstats id only, never blended into this table (R3).

### Run 1 -- build host, commit `cd1e85a`

- **Board:** none. This run is a build, not a device test. The build host is 4c/8t, 11 GB, 16 GB
  swap; the image is built for `MACHINE=raspberrypi0-wifi`.
- **Image commit:** `cd1e85a3e7f563d5449eb5d80447bba39ab8177e`, recorded in
  `build/coldbuild/host-start.txt` by `git rev-parse HEAD` at launch (the `#176 cold_build_time:
  record the pre-run proofs` commit), confirmed as HEAD by `tools/write-build-rev.sh`'s
  `KIOSK_BUILDINFO_REV` (`tools/kas-run.sh` runs it before every build).
- **Scripts deployed, each ONE-OFF, committed beside this README:**
  - `write-overlay.sh` -- writes the `TMPDIR`/`SSTATE_DIR`/`BUILDHISTORY_DIR` overlay.
  - `proofs.sh` -- the three pre-run proofs (a)-(c), output under `proofs/`.
  - `run-cold-build.sh` -- launches the build and `watch.sh`, detached.
  - `watch.sh` -- 60 s memory/progress samples and the restart trigger, in `watch.log`.
  - `restart-webkit.sh` -- the restart rule's stop/cleansstate/resume (not exercised this run).
  - `collect.sh` -- packs the evidence below after the run.
  - `parse_buildstats.py` -- the two reporting figures, checked against the known prior run
    `20261002222637` (9h44m49s wall, 21960 s WebKit `do_compile`) -- reproduced exactly (see
    [Findings](#findings), and the raw output at
    `parse-report-20261002222637-validation.md`) before being trusted on this run.
  - `ninja-log-compare.py` -- matched-by-filename `.ninja_log` throughput/per-unit comparison
    against the two surviving prior logs, output captured to
    `ninja-log-compare-20261004023340.txt` (see
    [Supporting evidence](#supporting-evidence-ninja_log-throughput-vs-the-two-priors)).
- **Procedure:** pipeline confirmed idle (`wisekiosk-pipeline.service` inactive, lock free), then
  `just pipeline-off`; `proofs.sh` (all three checks passed); `run-cold-build.sh`, which refused
  once on a non-empty `build/coldbuild/tmp` left by `proofs.sh`'s own `bitbake -e`/`-g` calls (no
  `work/` or `buildstats/` in it -- bitbake's own parse-cache bookkeeping, not stale build state),
  cleared and relaunched as a genuine fresh cold run. It records host state, writes the overlay, and
  launches `tools/kas-run.sh build kiosk-zero-w.yaml:build/coldbuild/zz-coldbuild.yaml` against an
  empty `build/coldbuild/{tmp,sstate-cache,buildhistory}`. `watch.sh` ran alongside it the whole
  time. `collect.sh` afterward, then `just pipeline-on`.
- **Raw capture:** `buildstats-20261004023340.tar.xz`, `parse-report-20261004023340.md`,
  `webkit-compile-line-20261004023340.txt`, `manifest-packages-20261004023340.txt`,
  `local-conf-dirs-20261004023340.txt`, `proofs/{a,b,c}-*.txt`, `watch-20261004023340.log`,
  `ninja-log-compare-20261004023340.txt`, and the prior-run validation
  `parse-report-20261002222637-validation.md`.

## Configuration under test

The tree facts this run rests on:

- **Icon theme dropped.** `kiosk-zero-w.yaml`'s `trim:` block adds
  `RRECOMMENDS:gtk+3:remove = "adwaita-icon-theme-symbolic"`, which takes `adwaita-icon-theme`,
  `librsvg`, `librsvg-native`, `rust-native`, `rust-llvm-native` and `cargo-native` out of the build
  graph and the image (confirmed: Findings). WebKit's own broken-image and form-control icons are
  compiled into WebCore, so nothing in the running kiosk depends on the removed theme.
  `hicolor-icon-theme` does **not** drop out, contrary to the plan's prediction -- see Findings.
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
- **Restart rule: active thrash or an OOM-kill only.** `/proc/pressure/memory` `full avg300` above 10
  for 15 consecutive 60 s samples while `do_compile` runs, or an OOM-kill. Elapsed `do_compile` time
  alone never triggers a restart -- withdrawn after launch, before this run reached it; `watch.sh`'s
  elapsed-time trigger is removed as part of this PR (it still logs elapsed time, just never flags
  it as a problem).

## Metrics

### Run 1 -- build host, commit `cd1e85a`, buildstats `20261004023340`

Source: `parse-report-20261004023340.md`, `watch-20261004023340.log`, `webkit-compile-line-20261004023340.txt`.

| metric | value |
|---|---|
| cold full build (first task `Started` -> `do_image_complete` `Ended`) | **5h46m37s (20797.2s)** |
| WebKit rebuild (`webkitgtk3:do_configure` `Started` -> `do_image_complete` `Ended`) | **3h13m01s (11581.4s)** |
| `webkitgtk3:do_compile` wall time | 3h05m44s (11144s) |
| `webkitgtk3:do_compile` peak child RSS | 3774032 KB (3.60 GiB) |
| solo-window minutes (exactly 1 task in flight) | 100 min (10 of 36 ten-minute buckets) |
| `watch.log` minimum `MemAvailable` | 998428 KB (0.95 GiB), at 08:14:27Z, during final image packaging (after `do_compile`) |
| `watch.log` minimum `MemAvailable` during `webkitgtk3:do_compile` itself | ~1119716 KB (1.07 GiB) |
| `watch.log` maximum `/proc/pressure/memory` `full avg300` | 1.84 (restart threshold is 10 for 15 consecutive samples; never approached) |
| tasks attempted / rerun-not-needed / succeeded | 7270 / 0 / 7270 (buildstats: 7245 real + setscene) |
| restart triggers fired | none (no PSI streak, no OOM-kill, no `Killed` in `run.log`) |

### Criteria proofs (ticket criteria 1-2, from this run)

- `log.do_compile`'s build-command line: **`Run Build Command(s): ninja -v -j 6 all`**
  (`webkit-compile-line-20261004023340.txt`).
- Its compile line carries no `-g`/`-g1` token: flags present are
  `-feliminate-unused-debug-types -fcanon-prefix-map -fmacro-prefix-map=... -fdebug-prefix-map=...`
  -- the prefix-map tokens are present, no debug-info flag is.
- None of the six removed recipes (`adwaita-icon-theme`, `librsvg`, `librsvg-native`,
  `rust-native`, `rust-llvm-native`, `cargo-native`) appears among this run's 455 buildstats recipe
  directories.
- Neither `adwaita-icon-theme` nor `librsvg` appears in `manifest-packages-20261004023340.txt`
  (2187 installed packages).

## Findings

**`parse_buildstats.py` reproduces the known prior run exactly.** Run against buildstats
`20261002222637` (a different build tree on this host, pre-existing from before this
investigation), it reports wall time 9h44m49s (35089.3s) and `webkitgtk3:do_compile` 21960s --
both match the figures established in discovery exactly. Raw output:
`parse-report-20261002222637-validation.md`, committed beside this README. This check was run once,
before Run 1's own output was trusted.

**Hypothesis: "the three levers together cut the cold build from ~9h44m worst case to a few
hours" -- CONFIRMED.** Cold full build measured at 5h46m37s, against priors of 6h51m-9h44m49s (all
at `-j2`, with debug info, with the icon theme); `webkitgtk3:do_compile` alone fell to 11144s against
the priors' 17317-21960s.

**Hypothesis: "`hicolor-icon-theme` also drops out" -- DROPPED.** The plan predicted it would,
reasoning it rode in only via `adwaita-icon-theme`. The manifest shows `hicolor-icon-theme 0.17-r0`
installed. Reading `sources/poky/meta/classes-recipe/gtk-icon-cache.bbclass:19,68-70`: any package
that installs files under an icon-theme directory structure gets a hard `RDEPENDS` on
`hicolor-icon-theme`, auto-detected per-package, independent of any `RRECOMMENDS` chain --
`gtk+3.inc:87-88` ships `${datadir}/icons/hicolor/*/apps/gtk3-demo*.png`, which is enough to trigger
it on its own. `adwaita-icon-theme` and `librsvg` (and the rust toolchain chain behind them) are
confirmed absent, which is what the ticket's `-j`/debug/time goal rests on;
`hicolor-icon-theme` itself carries no rust or `librsvg` dependency, so this does not cost build
time -- it is a correction to the plan's prediction, not a defect in the lever.

**Hypothesis: "`-j6` + no debug info makes WebKit faster, full stop" -- PARTIALLY CONFIRMED, with a
real tradeoff underneath the headline.** See [Supporting evidence](#supporting-evidence-ninjalog-throughput-vs-the-two-priors):
overall throughput is 1.33x-1.97x faster (depends on which prior), but per individual `.o` compile
unit `-j6` is 1.45x-2.06x *slower* than `-j2` -- six concurrent heavy WebKit compiles on an 8-vCPU
host thin out each job's share of CPU cache and memory bandwidth. The 3x increase in concurrent jobs
more than offsets the per-job slowdown, which is the throughput win actually measured. This is a
genuine latency-vs-throughput tradeoff, not a regression hiding under a good headline number.

**The three WARNING messages are pre-existing and unrelated to W1.** None reference `gtk+3`,
`webkitgtk3`, `adwaita`, `librsvg`, debug flags or `PARALLEL_MAKE`:
1. `meta-virtualization` layer included but `virtualization` not in `DISTRO_FEATURES` -- a layer
   inclusion notice, present regardless of this ticket's changes.
2. Host distribution `debian-13` not validated with this bitbake version -- a host-environment
   notice.
3. `systemd-1_255.22-r0 do_install`: `/home/root` as root's home directory is not fully supported by
   systemd -- a pre-existing `systemd` packaging warning, unrelated to any recipe this ticket
   touches.

**Observation, not a change: memory headroom for a higher `-j` is tighter than a mid-build snapshot
suggested.** `watch.log`'s true minimum `MemAvailable` over the whole run is 0.95 GiB (final image
packaging, after WebKit finished) and 1.07 GiB during `webkitgtk3:do_compile` itself -- not the
~3.8 GiB an earlier in-progress reading implied, taken before `do_compile`'s own profile and the
packaging-phase dip had played out. `-j6` is already consuming most of this host's headroom during
`do_compile`, not comfortably under it; the data does **not** support "a higher `-j` may fit"
without more memory or accepting the PSI-thrash risk the restart rule exists to catch. Untested
either way -- `-j8` was never tried, per the plan.

## Supporting evidence: `.ninja_log` throughput vs. the two priors

Two of the three prior buildstats runs' `webkitgtk3` work directories were overwritten in place
before this investigation began, so only two `.ninja_log`s survive: `20260929042915` (priorA,
do_compile 14815.49s) and `20261002222637` (priorB, 21960.33s, cited elsewhere in this document).
**The two priors disagree with each other by 1.48x on the same recipe/version/flags** -- they were
not run under identical host load -- so every ratio below is reported against both.

`ninja-log-compare.py` matches by output **filename**, not ninja edge index -- a `-j2` vs `-j6`
schedule legitimately reorders independent work, and matching by edge count made `bin/WebKitWebDriver`
(which links only against WTF and system libraries, not `libwebkit2gtk`, so it has no true
dependency on the long compile tail) look like a false "straggler" that collapsed the comparison to
a few seconds. Restricting to the real long-pole work -- single-output `.o` compile edges under
`Source/{WebCore,JavaScriptCore,WebKit,WTF,bmalloc,WebKitLegacy}/`, excluding `WebDriver/`, `po/*.gmo`
and `MiniBrowser` -- gives a stable comparison over the full, completed set (1721 of 1721 matched
against both priors, essentially the entire core compile graph):

| vs | matched `.o` edges | per-unit mean: current | per-unit mean: prior | current/prior (per-unit) | throughput span: current | throughput span: prior | prior/current (throughput) |
|---|---:|---:|---:|---:|---:|---:|---:|
| priorA `20260929042915` | 1721 | 33395 ms | 16221 ms | **2.06x slower** | 11102.0s | 14767.7s | **1.33x faster** |
| priorB `20261002222637` | 1721 | 33395 ms | 23064 ms | **1.45x slower** | 11102.0s | 21909.5s | **1.97x faster** |

**Per compile unit, `-j6` is 1.45x-2.06x slower than `-j2`; summed across the whole matched set,
`-j6`'s throughput is 1.33x-1.97x faster.** Both are true at once: six concurrent compiles each run
slower (CPU cache and memory bandwidth are shared six ways instead of two), but three times as many
of them land per unit of wall time, and the net is the 1.33x-1.97x the headline cold-full and
WebKit-rebuild figures above are made of. The script is `ninja-log-compare.py`, committed beside
this README; its raw output is `ninja-log-compare-20261004023340.txt`, also committed -- this
table is transcribed from that file, not hand-computed. The three `.ninja_log` *inputs* are not
committed (each ~2.7 MB, and two live on build trees outside this repo); its matched edge count
(1721/1721 against both priors) is what confirms the comparison covers the real compile graph, not
a filtered or lucky subset.

## Changes configured as a result

**Code change**, this branch, closing #176:

- `kiosk-zero-w.yaml`'s `parallel:` block: `PARALLEL_MAKE:pn-webkitgtk3 = "-j6"` (was `-j2`) and
  new `DEBUG_FLAGS:remove:pn-webkitgtk3 = "-g -g1"`.
- `kiosk-zero-w.yaml`'s `trim:` block: new `RRECOMMENDS:gtk+3:remove = "adwaita-icon-theme-symbolic"`.
- The restart rule ships as thrash-or-OOM only (the elapsed-time trigger, stated in the original
  plan, was withdrawn by the owner after this run launched and before it was reached).
- This measurement harness (`proofs.sh`, `write-overlay.sh`, `run-cold-build.sh`, `watch.sh`,
  `restart-webkit.sh`, `collect.sh`, `parse_buildstats.py`, `ninja-log-compare.py`), frozen at
  merge like the rest of this directory.
- The replaced figures (cold full build, WebKit-invalidating rebuild) are placed in README.md,
  CONTRIBUTING.md, CLAUDE.md, `.claude/skills/measure-first/SKILL.md`,
  `.claude/hooks/guard-design-surfaces.py`, `guard.sh` and `precompact.sh` wherever they meant the
  prior ~4.5 h figure.
