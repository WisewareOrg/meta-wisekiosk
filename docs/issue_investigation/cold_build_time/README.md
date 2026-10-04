# What does a cold-cache full build cost, and how far do the icon-theme, WebKit-debug and WebKit-parallelism levers cut it?

| | |
|---|---|
| **Issue** | #176 WebKit build time |
| **Status** | concluded → code change |
| **Opened / concluded** | 2026-10-03 / 2026-10-04 |

This is the first measured **cold** build (empty `TMPDIR`/`SSTATE_DIR`): 7245 real tasks, 0 restored
from sstate. Three prior buildstats runs (`20260828163401`, `20260930184746`, `20261002222637`),
all at the WebKit `PARALLEL_MAKE` of `-j2`, were **partial rebuilds** -- 321, 1493 and 90 tasks
respectively were restored from sstate rather than executed -- and still took 6h51m-9h44m. In every
one, `webkitgtk3:do_compile` ran alone for 260 min with 6 of 8 threads idle, and the rest of the
build spent ~3.5 h on 6 bitbake slots with `rust-llvm-native:do_compile` (11471 s) as its longest
chain -- present only because `gtk+3` RRECOMMENDS `adwaita-icon-theme-symbolic`, which pulls in
`librsvg` and a Rust toolchain build nothing else in this image needs. This investigation measured
one cold build with the three agreed levers applied together: the icon theme dropped, WebKit built
without debug info, and WebKit's `PARALLEL_MAKE` raised to `-j6` on the
strength of a prior `-j6` build that completed on this host. **Result: cold full build ~6 h, WebKit
rebuild ~3 h.** The PSI and OOM-kill triggers never fired. The restart rule was reduced mid-run to
thrash-or-OOM only; its elapsed-time trigger fired once (`08:10:25Z`, `do_compile` past 3 h) and was
not acted on, because by then it was no longer a trigger anyone needed to act on -- see Findings.

## Test runs

| Run | Board (role) | Image commit | Harness / scripts | Result (1 line) |
|---|---|---|---|---|
| 1 | none -- build host, `MACHINE=raspberrypi0-wifi` | `cd1e85a3e7f563d5449eb5d80447bba39ab8177e` | `run-cold-build.sh`, `watch.sh`, `collect.sh`, `parse_buildstats.py` -- all one-off, committed here | Cold full 5h46m37s, WebKit rebuild 3h13m01s; PSI/OOM never fired, elapsed-time line logged but not acted on (see Findings) |

No restart was acted on (see [Findings](#findings)), so this is the only run; the three prior runs
are cited above and in Findings by buildstats id only, never blended into this table (R3).

### Run 1 -- build host, commit `cd1e85a`

- **Board:** none. This run is a build, not a device test. The build host is 4c/8t, 11 GB, 16 GB
  swap; the image is built for `MACHINE=raspberrypi0-wifi`.
- **Image commit:** `cd1e85a3e7f563d5449eb5d80447bba39ab8177e`, recorded in
  `build/coldbuild/host-start.txt` by `git rev-parse HEAD` at launch (the `#176 cold_build_time:
  record the pre-run proofs` commit), confirmed as HEAD by `tools/write-build-rev.sh`'s
  `KIOSK_BUILDINFO_REV` (`tools/kas-run.sh` runs it before every build).
- **Scripts deployed, each ONE-OFF, committed beside this README:**
  - `write-overlay.sh` -- writes the `TMPDIR`/`SSTATE_DIR`/`BUILDHISTORY_DIR` overlay.
  - `proofs.sh` -- the three pre-run proofs (a)-(c), output under `proofs/`. **The committed script
    is the post-review version** (a line-count assertion was added after review); it was re-run
    against the same config commit (`cd1e85a`) after the build and gave byte-identical output to
    the pre-launch run, so the committed `proofs/` evidence is this script's own output.
  - `run-cold-build.sh` -- launches the build and `watch.sh`, detached.
  - `watch.sh` -- 60 s memory/progress samples and the restart trigger, in `watch.log`. **The
    committed script differs from the one that ran:** the withdrawn elapsed-time `PROBLEM` line was
    removed, and the OOM `dmesg` check's `pipefail` hazard (below) was fixed. Neither change alters
    what this run's own `watch-20261004023340.log` already recorded.
  - `restart-webkit.sh` -- the restart rule's stop/cleansstate/resume; not exercised this run, left
    unchanged and unproven. Known, untested paths: its `docker ps` filter has no image tag (the
    image is pinned `:5.4`) and may not match; it never stops the old `watch.sh`; and there is a
    race between the prior run's `run.done` write and `restart-webkit.sh`'s log-rotation `mv`.
  - `collect.sh` -- packs the evidence below after the run.
  - `parse_buildstats.py` -- the two reporting figures, checked against each of the three named
    prior runs (see Findings) -- reproduced `20261002222637` exactly (9h44m49s wall, 21960 s WebKit
    `do_compile`) before being trusted on this run.
  - `ninja-log-compare.py` -- per-run `.ninja_log` stats for the real long-pole compile work,
    against two other runs at the prior `-j2`/`-g1` configuration (see
    [Supporting evidence](#supporting-evidence-per-compile-unit-cost-vs-two-other-ninja_logs)).
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
  `local-conf-dirs-20261004023340.txt`, `proofs/{a,b,c}-*.txt`, `watch-20261004023340.log`, the
  three prior-run validations `parse-report-20260828163401-validation.md`,
  `parse-report-20260930184746-validation.md` and `parse-report-20261002222637-validation.md`, the
  three compressed `.ninja_log`s `ninja_log-20261004023340.xz`, `ninja_log-20260929042915.xz` and
  `ninja_log-20261002222637.xz`, and `ninja-log-compare-20261004023340.txt`.

## Configuration under test

The tree facts this run rests on:

- **Icon theme dropped.** `kiosk-zero-w.yaml:355`'s `trim:` block adds
  `RRECOMMENDS:gtk+3:remove = "adwaita-icon-theme-symbolic"`, which takes `adwaita-icon-theme`,
  `librsvg`, `librsvg-native`, `rust-native`, `rust-llvm-native` and `cargo-native` out of the build
  graph and the image (confirmed: Findings). WebKit's own broken-image and form-control icons are
  compiled into WebCore, so nothing in the running kiosk depends on the removed theme.
  `hicolor-icon-theme` does **not** drop out, contrary to the plan's prediction -- see Findings.
- **WebKit built without debug info.** `kiosk-zero-w.yaml:374`'s `parallel:` block adds
  `DEBUG_FLAGS:remove:pn-webkitgtk3 = "-g -g1"`, on top of the recipe's own `-g1` (already in place
  before this ticket). `DEBUG_PREFIX_MAP`'s tokens are untouched, so the webkit `-dbg` packages become
  near-empty rather than disappearing, and nothing in this tree uses them.
- **WebKit's `PARALLEL_MAKE` raised to `-j6`.** Same `parallel:` block, `kiosk-zero-w.yaml:372`:
  `PARALLEL_MAKE:pn-webkitgtk3 = "-j6"`, matching the global `PARALLEL_MAKE` for the first time.
  `BB_NUMBER_THREADS`, the global `PARALLEL_MAKE`, `BB_PRESSURE_MAX_MEMORY` and every other recipe are
  untouched. `PARALLEL_MAKE` is in bitbake's own `BB_HASHEXCLUDE_COMMON` by default (poky's
  `bitbake.conf`), which is proof (c) -- the `-j` change cannot bust sstate hash equivalence.
- **"Cold" is an empty `TMPDIR`/`SSTATE_DIR`/`BUILDHISTORY_DIR`**, under `build/coldbuild/` via the
  generated `zz-coldbuild` `local_conf_header` block (sorts last by name, following
  `tools/rauc-rotate-build.sh`'s `${TOPDIR}` overlay precedent). `DL_DIR` and the pipeline's shared
  `build/sstate-cache` are untouched -- a download is not a build cost, and this investigation never
  writes the pipeline's own sstate.
- **GTK/WPE is out of scope here**, split to #185 WPE WebKit + cog evaluation.
- **Restart rule: active thrash or an OOM-kill only.** `/proc/pressure/memory` `full avg300` above 10
  for 15 consecutive 60 s samples while `do_compile` runs, or an OOM-kill. Elapsed `do_compile` time
  alone never triggers a restart -- withdrawn after this run launched, before anyone needed to act
  on the line it produced (see Findings). `watch.sh`'s elapsed-time trigger is removed as part of
  this PR; it still logs elapsed time, just never flags it as a problem.
- **7f9c56b's prior `-j6` thrash measurement is not reproduced here, and is confounded with the
  other two levers.** That commit recorded six parallel compilers swapping 22 million pages "against
  12 GB of RAM" at `-j6` with debug info still on. This run, `-j6` with no `-g`, peaked at PSI `full
  avg300` 1.84 -- no thrash. Whether that is because debug info's memory cost was the dominant factor,
  because this host's conditions differ from 7f9c56b's, or both, is not decided by this run alone.

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
| tasks attempted / rerun-not-needed / succeeded | 7270 / 0 / 7270 (7245 task files in buildstats, 0 setscene; the other 25 are `noexec` meta-tasks like `do_build`, which write no buildstats file) |
| PSI / OOM-kill triggers | neither fired (max PSI 1.84; 0 OOM lines in `dmesg`, 0 `Killed` in `run.log` and `log.do_compile`, checked independently of the watcher) |
| elapsed-time trigger (withdrawn, not acted on) | fired once, 08:10:25Z, `do_compile` at 10837s (~3.01h) |

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

**None of the three prior runs was itself cold.** `20260828163401` restored 321 tasks from sstate,
`20260930184746` restored 1493, and `20261002222637` restored 90 -- all partial rebuilds, confirmed
by running the committed `parse_buildstats.py` against each (buildstats directories still present
on this host; raw output committed as `parse-report-20260828163401-validation.md`,
`parse-report-20260930184746-validation.md` and `parse-report-20261002222637-validation.md`). This
run is the first one with 0 restored: 7245 real tasks, all executed. The three priors still took
6h51m-9h44m49s despite that partial reuse, against this run's full cold 5h46m37s.

**Hypothesis: "the three levers together cut the cold build well below the priors' range" --
CONFIRMED, and conservatively: the priors did less work than this run (sstate reuse) yet still took
longer, so the comparison favors them, not this run.** Cold full build measured at 5h46m37s,
against the three named priors' (`20260828163401`, `20260930184746`, `20261002222637`)
partial-rebuild range of 6h51m-9h44m49s; `webkitgtk3:do_compile` alone fell to 11144s against those
same three runs' do_compile range of 17318-21960s (`-j2`, debug info on, icon theme present, per
their own buildstats -- see the three validation reports above).

**Hypothesis: "`hicolor-icon-theme` also drops out" -- DROPPED.** The plan predicted it would,
reasoning it rode in only via `adwaita-icon-theme`. The manifest shows `hicolor-icon-theme 0.17-r0`
installed. The real edge, read from this run's own `buildhistory` dependency graph and `gcr3`'s
pkgdata: `gcr3` (pulled in independently of the icon-theme change) ships real icon files under
`/usr/share/icons/hicolor/`, and `gtk-icon-cache.bbclass` auto-adds a hard `RDEPENDS` on
`hicolor-icon-theme` to any package that does that -- `gcr3 -> hicolor-icon-theme`, nothing to do
with `gtk+3`'s own `RRECOMMENDS` or the removed `adwaita-icon-theme-symbolic` chain.
`adwaita-icon-theme` and `librsvg` (and the rust toolchain chain behind them) are confirmed absent,
which is what the ticket's `-j`/debug/time goal rests on; `hicolor-icon-theme` itself carries no
rust or `librsvg` dependency, so this does not cost build time -- it is a correction to the plan's
prediction, not a defect in the lever.

**The restart rule's PSI and OOM-kill triggers never fired; the withdrawn elapsed-time trigger did,
once, and nothing acted on it.** `watch.log` records `PROBLEM do_compile running longer than 3h
(10837s)` at `08:10:25Z`. The plan's elapsed-only trigger was withdrawn before anyone needed to
decide whether to act on that line, so no stop/cleansstate/resume happened and `restart-webkit.sh`
was never exercised. The next finding checks the OOM claim independently rather than resting on
`watch.sh`'s own report, since the watcher's `dmesg | grep -q` runs under `set -o pipefail` and a
hit anywhere in `dmesg`'s ring buffer would make `grep -q` exit early and `dmesg` die of `SIGPIPE` --
not wrong this run (no OOM line exists at all, see next), but not something to lean on either.

**No OOM-kill, checked independently of the watcher.** `dmesg`'s ring buffer covers this run's whole
window (oldest entry well before launch) and has zero `out of memory`/`killed process` lines;
`run.log` has zero `Killed` lines; `log.do_compile` has zero `Killed` lines. `watch.sh` itself is
unaffected this run (its own OOM check never had anything to match), but the README's no-OOM claim
rests on this independent check, not the watcher's report.

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

## Supporting evidence: per-compile-unit cost vs. two other `.ninja_log`s

Two `.ninja_log`s happen to survive at the same `-j2`/`-g1` configuration this ticket changed:
`20260929042915` (**not** one of the three canonical buildstats priors above -- a separately-dated
build that happens to share the same webkitgtk3 work dir and configuration) and `20261002222637`
(the third canonical prior, cited above). The other two canonical priors' own `.ninja_log`s --
`20260828163401` and `20260930184746` -- were already overwritten in place before this
investigation began. All three surviving `.ninja_log` inputs (this run's and both others') are
committed compressed beside this README --
`ninja_log-20261004023340.xz`, `ninja_log-20260929042915.xz`, `ninja_log-20261002222637.xz` -- since
the re-enabled pipeline and the post-merge cleanup would otherwise overwrite the two survivors.
`ninja-log-compare.py`, also committed, reads them (decompress first; its own usage comment gives
the exact command) and reports each run's own numbers, restricted to the real long-pole compile
work: single-output `.o` edges under `Source/{WebCore,JavaScriptCore,WebKit,WTF,bmalloc,WebKitLegacy}/`,
excluding `WebDriver/`, `po/*.gmo` and `MiniBrowser` (`WebKitWebDriver` links only against WTF and
system libraries, not `libwebkit2gtk`, so matching by raw output set or edge index makes it a false
"straggler" that distorts any comparison). Raw output: `ninja-log-compare-20261004023340.txt`.

Each run gets its own table (R3 -- these are never merged):

| this run (`20261004023340`, `-j6`, no `-g`) | |
|---|---|
| core `.o` edges | 1721 |
| mean duration | 33395 ms |
| total span | 11102.0 s |

| `20260929042915` (`-j2`, `-g1`; not a canonical prior) | |
|---|---|
| core `.o` edges | 1721 (1721 shared with this run) |
| mean duration | 16221 ms |
| total span | 14767.7 s |

| `20261002222637` (`-j2`, `-g1`; the third canonical prior) | |
|---|---|
| core `.o` edges | 1721 (1721 shared with this run) |
| mean duration | 23064 ms |
| total span | 21909.5 s |

In prose, from those three independent numbers: against `20260929042915`, this run's per-unit mean
is 2.06x higher (33395 / 16221 ms) while its total span is 1.33x shorter (14767.7 / 11102.0 s);
against `20261002222637`, per-unit mean is 1.45x higher (33395 / 23064 ms) and span 1.97x shorter
(21909.5 / 11102.0 s). Read together: **per individual compile unit, `-j6` runs slower than `-j2`
at both comparison points, while the whole matched set finishes faster** -- six concurrent jobs
each take longer, but enough more of them run at once to shorten the total. Why each job is slower
is not measured here; CPU-cache/memory-bandwidth contention among six concurrent compiles and
differing host load between these builds (recorded cold-full wall times already span 6h51m-9h44m
across the three canonical priors alone) are both plausible, unmeasured, and not distinguished by
this data.

## Changes configured as a result

**Code change**, this branch, closing #176:

- `kiosk-zero-w.yaml`'s `parallel:` block: `PARALLEL_MAKE:pn-webkitgtk3 = "-j6"` (was `-j2`) and
  new `DEBUG_FLAGS:remove:pn-webkitgtk3 = "-g -g1"`.
- `kiosk-zero-w.yaml`'s `trim:` block: new `RRECOMMENDS:gtk+3:remove = "adwaita-icon-theme-symbolic"`.
- The restart rule ships as thrash-or-OOM only (the elapsed-time trigger, stated in the original
  plan, was withdrawn after this run launched; it fired once at 08:10:25Z and nothing acted on it --
  see Findings).
- This measurement harness (`proofs.sh`, `write-overlay.sh`, `run-cold-build.sh`, `watch.sh`,
  `restart-webkit.sh`, `collect.sh`, `parse_buildstats.py`, `ninja-log-compare.py`), frozen at
  merge like the rest of this directory.
- The replaced `~4.5 h` figure is split by meaning across README.md, CONTRIBUTING.md, CLAUDE.md,
  `.claude/skills/measure-first/SKILL.md` and `.claude/hooks/guard-design-surfaces.py`: ~3 h for a
  webkit-local change (`PACKAGECONFIG`, a WebKit recipe edit), up to the cold full build (~6 h) for
  `DISTRO_FEATURES`, `MACHINE_FEATURES` or a poky/meta-openembedded pin bump. `guard.sh` and
  `precompact.sh` say "up to ~6 h" for any running build, without a WebKit-specific label, since
  they gate on a build being up rather than on what triggered it.
