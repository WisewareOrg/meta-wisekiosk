# What causes the bench board's hard reset mid-`rauc install`, and can the capture explain it?

| | |
|---|---|
| **Issue** | #245 Capture the board's logs during every image update |
| **Status** | open on cause; concluded → no change on the capture itself (judged sufficient) |
| **Opened / concluded** | 2026-10-30 / |

The bench board has hard-reset mid-`rauc install` about 3 times in 44 installs, with nothing
surviving the reset to say why (its journal is on the same SD card). `tools/kiosk-install.sh`
streams the board's kernel log, journal and once-a-second memory/load/SD/undervoltage stats to
the console across the install. Run 1 caught a real reset with the first two streams but no
stats, so there was nothing to judge the cause from. Run 2, after the `[stats]` stream was
added, passed clean and confirmed the capture's own ordering guarantee holds on a healthy
install. `loop.sh` then repeated `bench test` on this branch's head: batch 1 (40 runs) came back
clean, and batch 2 caught a reset at run 14 with `[stats]` running throughout. That reset's data
is judgeable: the board froze completely (network and `[stats]` both stopped at the same
moment) and the next kernel started too late for an instant power-dip reset, pointing instead to
a freeze followed by the 14 s hardware watchdog — timing evidence only, since the SoC's own
reset-cause register was not read. The capture is judged sufficient to carry this diagnosis; what
froze the board is still open, and is tracked as follow-up rather than blocking this ticket's
capture mechanism.

## Test runs

| Run | Board (role) | Image commit | Harness / scripts | Result (1 line) |
|---|---|---|---|---|
| 1 | bench · Pi Zero W | `fee57a946f4b256d1cd3999daf83a6b048f5fcbb` | `run-bench-test.sh` — one-off | Real mid-write reset; no `[stats]` stream yet |
| 2 | bench · Pi Zero W | `b6d537714dfc5efd85c2a80c88bfe44313f70cdd` | `run-bench-test.sh` — one-off | Clean install; capture ordering holds, `[stats]` lines land ~1/s |
| Batch 1 (runs 1-40) | bench · Pi Zero W | `b33eec2b6acc0a82e168064489dedaa261e857e2` | `loop.sh` — durable | 40/40 clean, no reset |
| Batch 2, runs 1-13 | bench · Pi Zero W | `b33eec2b6acc0a82e168064489dedaa261e857e2` | `loop.sh` — durable | 13/13 clean, no reset |
| Batch 2, run 14 | bench · Pi Zero W | `b33eec2b6acc0a82e168064489dedaa261e857e2` | `loop.sh` — durable | Reset: board froze completely, watchdog-window reboot ~11-19 s later |
| Batch 3, runs 1-34 | bench · Pi Zero W | `a4e94247dc2a82b681d2eb4c6307dbb31efa54e5` | `loop3.sh` — durable | 34/34 clean, no reset |
| Batch 3, run 35 | bench · Pi Zero W | `a4e94247dc2a82b681d2eb4c6307dbb31efa54e5` | `loop3.sh` — durable | Reset: whole-board freeze, confirmed network-independent; watchdog reboot ≥9.4 s later |
| Batch 4, runs 1-24 | bench · Pi Zero W | `3cb4f4cc0453941641e06610e3d93c7f4d906289` | `loop4.sh` — durable | 24/24 clean, no reset, `performance` governor pinned each run |
| Batch 4, run 25 | bench · Pi Zero W | `3cb4f4cc0453941641e06610e3d93c7f4d906289` | `loop4.sh` — durable | Reset: `freq=900000` in every heartbeat (DVFS not necessary for the reset); reset within ~0.3-2.3 s of the last heartbeat, unlike resets 2-3 |
| Batch 5, runs 1-25 | bench · Pi Zero W | `38e46c900e0c49c8b0e458b29acc8f015d1d2399` | `loop5.sh` — durable | 25/25 clean, no reset (run 17 a near-miss); loop ended on run 26's host_suite failing, not a reset or the cap -- see below |
| Batch 6, runs 1-20 | bench · Pi Zero W | `b9885af9da50d1fee2539e71005006345de0e940` | `loop6.sh` — durable | 20/20 clean, no reset (`bfq` scheduler) |
| Batch 7, runs 1-64 | bench · Pi Zero W | `8207d14bb4521043445fe44488985914e198411a` | `loop7.sh` — durable | 64/64 clean, no reset (`bfq` scheduler, cap raised to 90) |
| Batch 7, run 65 | bench · Pi Zero W | `8207d14bb4521043445fe44488985914e198411a` | `loop7.sh` — durable | Reset: PID1 never stalled (`wdt` never below 7); refutes PID1-starvation for this reset |
| Batch 8 baseline, attempt 1 | bench · Pi Zero W | `59969986d739e999652906f32c8ac9701624a926` | `batch8-baseline.sh` — one-off | Reset: no heartbeat armed (pre-loop8 perf baseline); same freeze-then-watchdog shape as resets 2/3/5 |
| Batch 8 bootstrap | bench · Pi Zero W | `595fb2bf6fb5a99d26871debaa78e67d6739bbe8` | `batch8-bootstrap.sh` — one-off | Clean install; puts the soft-lockup-detector kernel on bench ahead of `loop8.sh` |
| Batch 8, runs 1-5 | bench · Pi Zero W | `375fd0328152583f088bf42e795ce83583e26a0a` | `loop8.sh` — durable | 5/5 clean, no reset, no panic (soft-lockup detector armed at `watchdog_thresh=3`) |
| Batch 8, run 6 | bench · Pi Zero W | `375fd0328152583f088bf42e795ce83583e26a0a` | `loop8.sh` — durable | Reset, no panic: detector live but its ~6-8.4 s latency raced the ~6.5-7.7 s window this stop gave it; weak evidence only |
| Batch 8, panic-seed | bench · Pi Zero W | `375fd0328152583f088bf42e795ce83583e26a0a` | `sysrq-seed.sh` — one-off | Pass: `echo c > /proc/sysrq-trigger` lands a `dmesg-ramoops-0` with the crash; proves the capture path, not detection |
| Batch 9, attempt 1 | bench · Pi Zero W | `104ed752f298b65f43fc9e207e86b1f64eb41ecf` | `loop9.sh` — durable | **Voided**: run 1 reported a false `panic=yes` from the panic-seed's stale `dmesg-ramoops-0`, a `panic_recorded` defect (presence-only, no baseline) -- fixed in `loop9b.sh` |
| Batch 9, attempt 2, runs 1-56 | bench · Pi Zero W | `64a461bb759225812c9872ff570ac03dea37fa94` | `loop9b.sh` — durable | 56/56 clean, no reset, no panic |
| Batch 9, attempt 2, run 57 | bench · Pi Zero W | `64a461bb759225812c9872ff570ac03dea37fa94` | `loop9b.sh` — durable | **Voided**: host_suite's reproducibility gate refused (transient -- could not reach origin), and the resulting no-target_suite-record case crashed `target_suite_record` (`jq -e` exit 4) -- fixed in `loop9c.sh` |
| Batch 9, attempt 3, runs 1-15 | bench · Pi Zero W | `3bd3e8a9fc545ccdd6fc6ef04e04f0646634bc3a` | `loop9c.sh` — durable | 15/15 clean, no reset, no panic |
| Batch 9, attempt 3, run 16 | bench · Pi Zero W | `3bd3e8a9fc545ccdd6fc6ef04e04f0646634bc3a` | `loop9c.sh` — durable | **Voided** (handled as designed): the same transient gate refusal as attempt 2's run 57 |
| Batch 9, attempt 3, run 17 | bench · Pi Zero W | `3bd3e8a9fc545ccdd6fc6ef04e04f0646634bc3a` | `loop9c.sh` — durable | Reset: stop-to-reset window ≥11.4 s vs. the detector's 3.55 s worst case -- rules out an interrupts-on lockup strongly and unconditionally (detector confirmed to fire, below) |
| Soft-lockup detection seed | bench · Pi Zero W | `3ff13a8b272d6c447de0feb59a3acdbb94e48ca9` | `softlockup-seed.sh` — one-off | Pass: `chrt -f 99` busy loop with the RT throttle and fair server disabled trips the detector -- `dmesg-ramoops-0` holds the soft-lockup `BUG:` and panic |

### Run 1 — bench, commit `fee57a946f4b256d1cd3999daf83a6b048f5fcbb`

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Image commit:** `fee57a946f4b256d1cd3999daf83a6b048f5fcbb`, the sha `bench test` built and
  installed, read from `tests/target_suite`'s `--bench-candidate` argument in
  `records/20261030T042402Z/run.json`.
- **Scripts deployed:** `run-bench-test.sh` — ONE-OFF, committed here beside this README.
- **Procedure:** `./run-bench-test.sh fee57a946f4b256d1cd3999daf83a6b048f5fcbb` from
  `~/meta-wisekiosk`, under the pipeline lock. `bench test` builds, bundles, runs
  `tests/host_suite`, then `tests/target_suite`, whose `install_candidate` fixture runs
  `just kiosk-ota`.
- **Raw capture:** [`run1-reset.log`](run1-reset.log) — address- and hostname-redacted excerpt
  of `records/20261030T042402Z/report.jsonl`'s install item.

### Run 2 — bench, commit `b6d537714dfc5efd85c2a80c88bfe44313f70cdd`

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Image commit:** `b6d537714dfc5efd85c2a80c88bfe44313f70cdd`, read from
  `records/20261030T152422Z/run.json`.
- **Scripts deployed:** `run-bench-test.sh` — ONE-OFF, committed here beside this README (same
  script as Run 1, different sha).
- **Procedure:** `./run-bench-test.sh b6d537714dfc5efd85c2a80c88bfe44313f70cdd` from
  `~/meta-wisekiosk`, under the pipeline lock, run directly after Run 1.
- **Raw capture:** [`run2-clean.log`](run2-clean.log) — address- and hostname-redacted excerpt
  of `records/20261030T152422Z/report.jsonl`'s install item.

### Batches 1 and 2 — the loop

- **Harness:** [`loop.sh`](loop.sh) — DURABLE to this investigation, committed here. Runs
  `bench test <sha>` up to 40 times from `~/meta-wisekiosk`, under one hold of the pipeline
  lock for the whole loop (not per run), restoring the branch between runs. Appends one line per
  run to a summary file: `<host-ts> run=<i> sha=<sha> exit=<status> record=<records/<ts> dir>
  reset=<yes|no>`, and stops at the first `reset=yes`. Per-run detail (the full `report.jsonl`,
  `bench.log`) lives under that run's own `records/<ts>/` directory, not duplicated here.
- **Reset detection:** a run is `reset=yes` iff its `target_suite` record's install item shows a
  capture `session ended` line before its `capture stopped` line — the ordering
  `tools/kiosk-install.sh` guarantees on a clean run (Run 2) and that Run 1 violated. Checked
  against both known runs before trusting it in the loop (Run 1 → yes, Run 2 → no).
- **Batch 1:** `./loop.sh b33eec2b6acc0a82e168064489dedaa261e857e2 batch1-summary.txt`, launched
  detached. **Raw capture:** [`batch1-summary.txt`](batch1-summary.txt) — 40 runs, all
  `reset=no`.
- **Batch 2:** `./loop.sh b33eec2b6acc0a82e168064489dedaa261e857e2 batch2-summary.txt`, launched
  detached directly after batch 1 (same sha; the branch had already been exercised 40 times with
  no code change). **Raw capture:** [`batch2-summary.txt`](batch2-summary.txt) — runs 1-13
  `reset=no`, run 14 `reset=yes`; the loop stopped there.

### Batch 2, run 14 — the reset

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Image commit:** `b33eec2b6acc0a82e168064489dedaa261e857e2`, read from
  `records/20261031T005625Z/run.json`.
- **Scripts deployed, read-only, after the reset:** `board-read.sh`, `board-read2.sh`,
  `board-read3.sh` — each ONE-OFF, committed here beside this README, each taking the board's
  (redacted) address as its one argument and run under the pipeline lock.
  `reset2_window.py` — ONE-OFF, committed here, a read-only reduction over `records/` summarized
  in [`reset2-findings.md`](reset2-findings.md).
- **Procedure:** the loop's own `bench test` invocation for this run (no separate script); the
  three `board-read*.sh` scripts and `reset2_window.py` ran afterward, read-only, to analyze it.
- **Raw capture:** the full analysis, with every raw read and the full final-60-seconds
  `[stats]` dump quoted, is [`reset2-findings.md`](reset2-findings.md). Its own supporting raw
  outputs are committed beside it: [`board-read.out`](board-read.out),
  [`board-read2.out`](board-read2.out), [`board-read3.out`](board-read3.out),
  [`reset2-window.out`](reset2-window.out) (address- and hostname-redacted).
- **Follow-up, read-only, after the reset:** the SoC's firmware-held copy of its reset-cause
  register (`/proc/device-tree/chosen/bootloader/rsts`) and a read-only `pstore` mount
  (`mount -t pstore -o ro pstore /sys/fs/pstore`, copied, then `umount`). **Raw capture:**
  [`reset2-console-ramoops-tail.log`](reset2-console-ramoops-tail.log) — the head and final 40
  lines of the recovered `console-ramoops-0` record (339 lines, 26609 B, md5
  `2480a8cebee507d46b8843476d6c9df6`), MAC redacted; the full 339-line copy is not committed.

### Batch 3 — the loop with diagnostics armed

- **Harness:** [`loop3.sh`](loop3.sh) — DURABLE, committed here. `loop.sh`'s structure plus two
  investigation-only steps run over ssh before each `bench test`, under the lock `loop3.sh`
  already holds: runtime `sysctl -w` for `kernel.printk_devkmsg` and the `hung_task_*` keys
  (logged and skipped if a key does not exist, not fatal; reverts at that boot's own reboot),
  and [`hb245.sh`](hb245.sh) launched detached — a once-a-second `/dev/kmsg` heartbeat carrying
  the same fields as the `[stats]` stream, so a line survives into `pstore`'s console record
  across a watchdog reset even when the network dies with the board. On a reset, before the
  summary line or the loop exiting, `pstore` is mounted read-only, copied byte-exact into that
  run's own `records/<ts>/pstore/`, and unmounted — nothing in `pstore` is ever deleted. Nothing
  here reaches `tools/kiosk-install.sh`, the image, or any recipe.
- **Run:** `./loop3.sh a4e94247dc2a82b681d2eb4c6307dbb31efa54e5 batch3-summary.txt
  root@<bench>`, launched detached. **Raw capture:** [`batch3-summary.txt`](batch3-summary.txt)
  — runs 1-34 `reset=no`, run 35 `reset=yes`; the loop stopped there.
- **A correction to `loop3.sh`'s own hand-validation note.** The loop's log shows `sysctl: write
  error: Invalid argument` for `kernel.printk_devkmsg=on` on every run, logged and skipped exactly
  as designed. Reset 35's board reads show the **current boot — which nothing armed — already
  boots with `printk_devkmsg=on`**, with no `printk.devkmsg` kernel cmdline token; the write's
  `EINVAL` most likely means the setting is locked, not that it failed to take. Who locks it is
  not established. It does not affect the finding: heartbeat integrity is measured directly (see
  below), not assumed from the sysctl's own exit status.

### Batch 3, run 35 — the reset

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Image commit:** `a4e94247dc2a82b681d2eb4c6307dbb31efa54e5`, read from
  `records/20261031T074356Z/run.json`.
- **Scripts deployed, read-only, after the reset:** `remote-read.sh` and `remote-read2.sh` — each
  ONE-OFF, committed here beside this README, run via `run-read.sh` (`flock -o -w 900 <lock> ssh
  <tools/kiosk-install.sh options> <bench> sh -s < <script>`; the same pattern for both, the
  second session substituting `remote-read2.sh`). `extract.py`, `window.py`, `batch3.py` and
  `episodes.py` — each ONE-OFF, committed here, read-only reductions over `records/` and the
  recovered `pstore` copy, summarized in [`reset3-findings.md`](reset3-findings.md). Their raw
  `.out` outputs were unredacted and are not committed.
- **Procedure:** the loop's own `bench test` invocation for this run (no separate script); the
  two `remote-read*.sh` sessions and the four Python reductions ran afterward, read-only, to
  analyze it.
- **Raw capture:** the full analysis, with every raw read and the final-30-seconds `[stats]`
  table, is [`reset3-findings.md`](reset3-findings.md). Redacted excerpts are committed beside
  it: [`reset3-host-tail.log`](reset3-host-tail.log) (the capture markers and each stream's last
  line) and [`reset3-console-ramoops-tail.log`](reset3-console-ramoops-tail.log) (the recovered
  `console-ramoops-0`'s head and final 80 lines, 861 lines / 91236 B total, md5
  `5a575b6fc3ef10b5b90b0f49ba637f0f`, MAC redacted; the full copy is not committed).

### Batch 4 — fixed-frequency experiment

- **Hypothesis.** Upstream `raspberrypi/linux#2555`'s reporters fixed Pi Zero instability with
  `force_turbo` (fixed frequency) plus `over_voltage`. This image caps the CPU at 900 MHz
  (`kiosk-cpufreq-cap.service`, `meta-wisekiosk/recipes-core/kiosk-cpufreq`) but leaves DVFS
  active at stock voltage. Batch 4 tests the fixed-frequency half at runtime, with no
  `over_voltage` change.
- **The one variable changed.** cpu0's `scaling_governor` is set to `performance` (fixed at
  `scaling_max_freq`, no scaling) on the board's current boot, before each run. Everything else
  — the sysctls and heartbeat `loop3.sh` already arms — is unchanged.
- **Baseline (the image default, read before anything was changed):** `scaling_governor=ondemand`,
  `scaling_cur_freq=900000`, `scaling_max_freq=900000`, `scaling_min_freq=700000`,
  `scaling_available_governors=conservative ondemand userspace powersave performance`.
  `kiosk-cpufreq-cap.service` is `active`/`enabled`.
- **Harness:** [`loop4.sh`](loop4.sh) — DURABLE, committed here. `loop3.sh`'s structure plus one
  added pre-run step, `set_governor`, run over ssh under the lock `loop4.sh` already holds: reads
  `scaling_available_governors`, sets `scaling_governor=performance`, and logs the readback
  (`scaling_governor`, `scaling_cur_freq`, `scaling_max_freq`). **Not optional:** if `performance`
  is not available, the script stops rather than substitute another governor. Uses
  [`hb245-freq.sh`](hb245-freq.sh) — `hb245.sh` with one field appended, the live
  `scaling_cur_freq`, as `freq=` at the end of the heartbeat line; every existing field and its
  order is unchanged, so earlier batches' heartbeat lines are unaffected.
- **Cap and stopping rule:** 90 runs, stopping at the first `reset=yes` (`loop3.sh`'s own reset
  detection and `pstore` capture, unchanged).
- Hand-validated against bench before launch: `set_governor` reads back
  `scaling_governor=performance scaling_cur_freq=900000 scaling_max_freq=900000`, and
  `hb245-freq.sh`'s heartbeat lines carry `freq=900000` appended after `uv=`, every other field
  in place.
- **Result:** 24/24 clean, then a reset at run 25. `freq=900000` holds in all 338 heartbeats
  up to the last line — the CPU never left 900 MHz. Governor was back to `ondemand` on the next
  boot, confirming the change was runtime-only as designed. See
  [`reset4-findings.md`](reset4-findings.md) and the Metrics/Findings sections below.

### Batch 4, run 25 — the reset

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Image commit:** `3cb4f4cc0453941641e06610e3d93c7f4d906289`, read from
  `records/20261031T121511Z/run.json`.
- **Scripts deployed, read-only, after the reset:** [`reset4-remote-read.sh`](reset4-remote-read.sh)
  and [`reset4-remote-read2.sh`](reset4-remote-read2.sh) — each ONE-OFF, committed here, renamed
  from `remote-read.sh`/`remote-read2.sh` to avoid colliding with reset 3's same-named scripts
  already in this directory; each run once over ssh, the same flock+ssh pattern as reset 3.
  [`extract.py`](extract.py), [`window.py`](window.py) and [`episodes.py`](episodes.py) — the
  committed reset-3 scripts, reused as-is except `episodes.py`'s hardcoded summary path,
  repointed at batch 4's summary for this reset (not a different script). `batch4.py` and
  `endphase.py` — each ONE-OFF, committed here, read-only per-run reductions over `records/` and
  the recovered `pstore` copy. Summarized in [`reset4-findings.md`](reset4-findings.md). Their
  raw `.out` outputs were unredacted and are not committed.
- **Procedure:** the loop's own `bench test` invocation for this run (no separate script); the
  two `reset4-remote-read*.sh` sessions and the Python reductions ran afterward, read-only, to
  analyze it.
- **Raw capture:** the full analysis, with every raw read, is
  [`reset4-findings.md`](reset4-findings.md). Redacted excerpts are committed beside it:
  [`reset4-host-tail.log`](reset4-host-tail.log) (the capture markers and each stream's last
  line) and [`reset4-console-ramoops-tail.log`](reset4-console-ramoops-tail.log) (the recovered
  `console-ramoops-0`'s head and final 40 lines, 929 lines / 103428 B total, md5
  `9da1a586250410bbfdf345b528b18fcb`, MAC redacted; the full copy is not committed).

### Batch 5 — watchdog and PID1 observation

- **Hypothesis.** One reading of resets 2-4 is that the hardware watchdog fires because PID1
  (systemd, the only pet source) stops petting it for ≥14 s, while the rest of the kernel, the
  heartbeat and I/O run on — consistent with reset 4's short R, and requiring reset 2/3's
  userspace to have stalled wholesale with khungtaskd's due report going unseen. The competing
  reading is a supply sag that resets the SoC directly. Batch 5 adds the two read-only
  observables that would separate them: the watchdog's own countdown, and PID1's state.
- **What's observed; no variable changed.** The board stays at the image default `ondemand`
  governor — batch 5 is back at the baseline conditions batches 1-3 ran under (no `performance`
  pin, unlike batch 4). The heartbeat gains four read-only fields, nothing is written to the
  watchdog, and nothing else about the install path changes.
- **Harness:** [`loop5.sh`](loop5.sh) — DURABLE, committed here. `loop3.sh`'s diagnostics
  (hung-task sysctls, the heartbeat) with no governor step. Checks once, before the loop, that
  `/sys/class/watchdog/watchdog0/timeleft` is readable — **not optional:** stops the whole
  script, not just a run, if it is absent or unreadable, rather than substitute another source.
  Uses [`hb245-wdt.sh`](hb245-wdt.sh) — `hb245-freq.sh` with four fields appended, in order:
  `wdt=` (`watchdog0/timeleft`), `p1=` (field 3, state, of `/proc/1/stat`), `p1wchan=`
  (`/proc/1/wchan`), `p1majflt=` (field 12, majflt, of `/proc/1/stat`). Every existing field and
  its order is unchanged, so earlier batches' heartbeat lines are unaffected.
- **Cap and stopping rule:** 90 runs, stopping at the first `reset=yes` (`loop3.sh`'s own reset
  detection and `pstore` capture, unchanged).
- Hand-validated against bench before launch: the missing-file check was proven both ways (a
  real path passes; a seeded nonexistent path stops the script, exit 1, with nothing after it
  running); `hb245-wdt.sh`'s heartbeat lines carry all four new fields in order after `freq=`,
  and `wdt=` was observed counting down (11, 10, 9) then resetting to 13 as systemd pets it.
- **Result:** 25/25 clean, no reset. **Run 17 (clean, `records/20261031T154133Z`) is a
  near-miss.** PID1 went from `S`/`do_epoll_wait` to `D`/`__ext4_find_entry` for about 3.9 s
  (board `[601.31]`-`[603.94]`) while the install's write kept moving; `wdt` fell from 12 to
  **4**, well below the 7-8 floor a heartbeat shows between pets on a healthy sample, before
  jumping back to 12 once PID1 unblocked and petted the watchdog. See
  [`run17-near-miss.log`](run17-near-miss.log) (the `[kernel]`-stream heartbeats, hung-task
  call-trace repeats omitted) and [`metrics.py`](metrics.py) (committed here, a per-run reducer
  over a record's `report.jsonl`: install window, max `[stats]`/heartbeat gap, min `wdt`, every
  distinct non-`S` PID1 state with its `wchan`, and seconds spent in `D` -- run 17:
  `min_wdt=4 p1_d_seconds=3.5`, one row per run, never aggregated).
- **How the loop ended.** Not a reset and not the 90-run cap: run 26's `tests/host_suite`
  reproducibility-gate check failed (`records/20261031T171121Z/run.json`, exit 1,
  `tools/reproducibility-gate.sh --image ...` returned 1) because this checkout's working tree
  was staged-dirty at that moment -- batch-6 prep (this README update, `loop6.sh`, `metrics.py`,
  `run17-near-miss.log`) was being `git add`ed and committed (`bea43e4`, landed
  2026-10-31T17:13:03Z) while loop5 was still running, which the brief that asked for it should
  not have (owner's own correction). `bench test`'s own `CandidateFailure` on that exit code is
  caught by loop5.sh's `|| status=$?`, so this did not by itself end the script; loop5.sh's own
  LOG stops immediately after, with no further output, most likely at the same `git checkout -q
  "$branch"` restore line hitting the same staged, uncommitted tree. The board was undisturbed
  (confirmed read-only afterward: idle, freshly rebooted from run 25's own successful install)
  and nothing was lost -- run 26 produced no target_suite record and is not counted as a run.
  Checkouts are not edited while a loop runs, going forward.

### Batch 6 -- BFQ scheduler experiment

- **Hypothesis.** `rauc`'s bulk image copy is a buffered write with no `O_DIRECT` and one
  `fsync` at the end, under `mmcblk0`'s default `mq-deadline` elevator; PID1's own small
  filesystem reads (run 17's `__ext4_find_entry`) queue behind that write. `BFQ` prioritises
  synchronous reads over large async writes by design. Batch 6 tests whether switching the
  elevator shortens PID1's read stalls.
- **The one variable changed.** `mmcblk0`'s IO scheduler is set to `bfq` on the board's current
  boot, before each run. Governor stays `ondemand` (unlike batch 4); no `IOWeight`, no dirty
  limits. Everything else -- the sysctls and the `hb245-wdt.sh` heartbeat batch 5 already arms --
  is unchanged, so its fields are directly comparable run-by-run against batches 3 and 5.
- **Harness:** [`loop6.sh`](loop6.sh) -- DURABLE, committed here. `loop5.sh`'s diagnostics plus
  one added pre-run step, `set_scheduler`: reads `queue/scheduler`'s available list, sets it to
  `bfq`, and logs the readback. **Not optional:** if `bfq` is not listed, the script stops
  rather than substitute another scheduler. Two hardening additions, added before this batch's
  launch and in effect for every run below: an `ERR` trap that names the failing line and exit
  status on any unexpected failure, so a stop is never silent; and `wait_for_board`, which retries
  a trivial ssh every 10 s (up to 30 tries, 5 min) before each run's pre-run diagnostics and stops
  the loop, logging why, if the board never answers, rather than skip diagnostics and carry on.
- **Metric.** Each run's `metrics.py` row -- max `[stats]` gap, max heartbeat gap, min `wdt` --
  compared run by run against batches 3 and 5's same fields, never pooled across batches.
- **Cap and stopping rule:** 20 runs, stopping at the first `reset=yes` (`loop3.sh`'s own reset
  detection and `pstore` capture, unchanged).
- Hand-validated against bench before launch (board idle, batch 5 fully stopped): the baseline
  scheduler reads `none [mq-deadline] kyber bfq`; `set_scheduler` reads back
  `scheduler=none mq-deadline kyber [bfq]`; the availability check was also proven to fail on a
  seeded list without `bfq`. `wait_for_board` was proven against the live board (answers on the
  first try) separately from the hardening fix. Found and cleaned up a leftover `hb245.sh`
  heartbeat process on the board from batch 5's aborted run 26 (its install never reached a
  reboot, so the process never died); it is killed and its script removed.
- **Result:** 20/20 clean, no reset -- the cap exhausted with none caught. **Raw capture:**
  [`batch6-summary.txt`](batch6-summary.txt). **Per-run metrics**, one row per run (`metrics.py`
  over each run's own record, never aggregated), full output in
  [`batch6-metrics.txt`](batch6-metrics.txt):

  | run | record | max `[stats]` gap (s) | max heartbeat gap (s) | min `wdt` | PID1 `D`-state (s) |
  |---|---|---|---|---|---|
  | 1 | `records/20261031T174046Z` | 1.73 | 2.98 | 7 | 3.6 |
  | 2 | `records/20261031T175132Z` | 1.42 | 1.45 | 7 | 0.0 |
  | 3 | `records/20261031T180555Z` | 1.43 | 1.44 | 7 | 0.0 |
  | 4 | `records/20261031T181519Z` | 1.39 | 1.62 | 7 | 0.0 |
  | 5 | `records/20261031T182516Z` | 1.30 | 1.51 | 7 | 0.0 |
  | 6 | `records/20261031T183608Z` | 1.21 | 1.54 | 7 | 0.0 |
  | 7 | `records/20261031T184553Z` | 1.37 | 1.99 | 7 | 0.0 |
  | 8 | `records/20261031T185550Z` | 1.56 | 1.86 | 7 | 0.0 |
  | 9 | `records/20261031T190533Z` | 1.28 | 1.83 | 7 | 0.0 |
  | 10 | `records/20261031T191521Z` | 1.38 | 1.81 | 7 | 0.0 |
  | 11 | `records/20261031T192503Z` | 1.42 | 1.80 | 7 | 0.0 |
  | 12 | `records/20261031T193511Z` | 1.34 | 1.95 | 7 | 0.0 |
  | 13 | `records/20261031T194518Z` | 1.21 | 1.53 | 7 | 0.0 |
  | 14 | `records/20261031T195504Z` | 1.42 | 1.62 | 7 | 0.0 |
  | 15 | `records/20261031T200419Z` | 1.22 | 1.46 | 7 | 0.0 |
  | 16 | `records/20261031T201404Z` | 1.15 | 1.31 | 7 | 0.0 |
  | 17 | `records/20261031T202332Z` | 1.44 | 1.93 | 7 | 0.0 |
  | 18 | `records/20261031T203403Z` | 1.24 | 1.38 | 7 | 0.0 |
  | 19 | `records/20261031T204353Z` | 1.52 | 1.63 | 7 | 1.5 |
  | 20 | `records/20261031T205409Z` | 1.28 | 1.42 | 7 | 0.0 |

  **Comparison against the default `mq-deadline` elevator (batches 3 and 5), counted with
  `metrics.py` over each batch's own committed summary -- [`batch3-summary.txt`](batch3-summary.txt)'s
  34 clean runs (excluding run 35, the reset) and [`batch5-summary.txt`](batch5-summary.txt)'s 25:**
  max `[stats]` gap &ge; 4 s in 15/34 (batch 3) and 8/25 (batch 5) runs, versus **0/20** under
  `bfq`; max `[stats]` gap &lt; 2 s in 9/34 and 7/25, versus **20/20** under `bfq` -- every batch-6
  run stayed under 2 s. `min_wdt` never dropped below 7 in any batch-6 run (batch 5's own floor
  between pets on a healthy sample; batch 5 saw it fall to 4 twice, including run 17's near-miss).
  Two batch-6 runs show nonzero PID1 `D`-state time (run 1: 3.6 s, run 19: 1.5 s) against batch 5's
  three nonzero runs of 25 (including run 17's 3.5 s) -- stalls still happen under `bfq`, but
  shorter and without a watchdog headroom drop in this batch.
- **Conclusion.** `bfq` removes the multi-second `[stats]`/heartbeat gaps this investigation has
  been tracking since batch 3 -- every batch-6 run stayed under 2 s, where 15-32% of default-
  elevator runs hit 4 s or more. Whether it removes the *reset* is untested: the default elevator's
  pooled reset rate across batches 1-4 is 3 resets in 114 runs (40 + 14 + 35 + 25) &asymp; 2.6%, so
  batch 6's cap (20 runs, chosen to fit one lock-holding session) is well under the run count
  needed to say anything about the reset itself -- 20/20 clean is the expected outcome whether or
  not `bfq` changes the reset probability at all. Batch 7 repeats the same lever at a cap (90
  runs) sized against that baseline.

### Batch 7 -- BFQ scheduler, run to the reset-rate baseline

- **Hypothesis.** Batch 6 showed `bfq` removes the multi-second `[stats]`/heartbeat read-stall
  gaps at 20 runs, but 20 is well under the baseline reset rate (batches 1-4, default elevator: 3
  resets in 114 runs &asymp; 2.6%) and so cannot say anything about the reset itself. Batch 7 runs
  the same lever long enough to compare against that baseline: if `bfq` removes the reset along
  with the stalls, batch 7 should clear 90 runs clean; if the reset shares the stalls' mechanism
  only loosely, or not at all, a reset can still land inside 90 runs at roughly the baseline rate.
- **The one variable changed.** None, relative to batch 6 -- same lever (`mmcblk0`'s IO scheduler
  set to `bfq` on the board's current boot, before each run), same diagnostics
  (`hb245-wdt.sh`), same hardening (the `ERR` trap, `wait_for_board`). Only the cap changes.
- **Harness:** [`loop7.sh`](loop7.sh) -- DURABLE, committed here. `loop6.sh` verbatim except the
  cap, raised from 20 to 90 -- the same run count batch 3's cap used, and close to batch 1's 40 +
  batch 2's 14, so a full run is directly comparable to the baseline batches' totals.
- **Cap and stopping rule:** 90 runs, stopping at the first `reset=yes` (`loop3.sh`'s own reset
  detection and `pstore` capture, unchanged). **Raw capture:**
  [`batch7-summary.txt`](batch7-summary.txt); full per-run `metrics.py` output in
  [`batch7-metrics.txt`](batch7-metrics.txt).
- **Result:** 64/65 clean, then a reset at run 65. `bfq` against the default elevator: 1 reset in
  85 BFQ runs (batches 6+7, 1.2%) against 3 in 114 default-elevator runs (batches 1-4, 2.6%) --
  Fisher's exact two-sided p = 0.64, not distinguishable. BFQ still removed every near-miss (0 of
  85 runs dipped below `wdt`=7, against 2 of 25 on the default elevator in batch 5) and every
  `mmc_rescan` hung-task report (0 in 65 windows). See [`reset5-findings.md`](reset5-findings.md)
  and the Findings section below.

### Batch 7, run 65 — the reset

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Image commit:** `8207d14bb4521043445fe44488985914e198411a`, read from
  `records/20261101T090332Z/run.json`.
- **Scripts deployed, read-only, after the reset:** [`reset5-remote-read.sh`](reset5-remote-read.sh)
  — ONE-OFF, committed here, renamed from `remote-read.sh` to avoid colliding with batch 3's
  script already in this directory; run once over ssh under the pipeline lock.
  [`clocks.py`](clocks.py), [`final30.py`](final30.py), [`timing.py`](timing.py),
  [`pets.py`](pets.py), [`wdtrate.py`](wdtrate.py), [`wdtrate_d.py`](wdtrate_d.py),
  [`wdtrate_u.py`](wdtrate_u.py), [`progress.py`](progress.py), [`phase.py`](phase.py) and
  [`stamp.py`](stamp.py) — each ONE-OFF, committed here, read-only reductions over `records/`,
  the recovered `pstore` copy and the heartbeat stream. Summarized in
  [`reset5-findings.md`](reset5-findings.md). Their raw outputs were unredacted and are not
  committed.
- **Procedure:** the loop's own `bench test` invocation for this run (no separate script); the
  `reset5-remote-read.sh` session and the Python reductions ran afterward, read-only, to analyze
  it.
- **Raw capture:** the full analysis, with every raw read, is
  [`reset5-findings.md`](reset5-findings.md). Redacted excerpts are committed beside it:
  [`reset5-host-tail.log`](reset5-host-tail.log) (the capture markers and each stream's last
  line) and [`reset5-console-ramoops-tail.log`](reset5-console-ramoops-tail.log) (the recovered
  `console-ramoops-0`'s head and final 40 lines, 560 lines / 75236 B total, md5
  `45acb1a95645614d292bba75218b7f64`, MAC redacted; the full 560-line copy is not committed).
- **Verdict.** The watchdog/PID1 heartbeat ran to the last line and PID1 was never stalled: `S
  do_epoll_wait` in 220 of 221 heartbeats (one `R`), `wdt` never below the healthy floor of 7. The
  timing test rejects "the watchdog counted down from the last heartbeat" by about 7 s and agrees
  instead with "PID1 petted once more, then 14 s of silence" -- this is reset 3's shape, a
  whole-board stop the hardware watchdog recovered 14 s later. `PM_RSTS` read `0x20` again, the
  fourth consecutive checked reset to do so (n = 4 of 4). By mmc write-sector count the copy had
  reached ~26% of the image, the earliest of the five resets this investigation has caught
  (80/84/90/99% for resets 2-4).

### Batch 8 baseline, attempt 1 — the reset

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Image commit:** `59969986d739e999652906f32c8ac9701624a926`, read from
  `records/20261102T050109Z/run.json`.
- **Context.** This reset happened during batch 8's pre-change perf baseline: `bench test
  <HEAD>` on the then-current, unmodified HEAD, run once to put that image on bench
  before three `just bootprofile` passes -- before the soft-lockup kernel fragment and
  `loop8.sh` existed, with no heartbeat and no diagnostic sysctls armed (confirmed on the board:
  `hung_task_timeout_secs=120`, the image default; zero `hb245` processes). Without that
  instrumentation this reset cannot say anything new about the PID1-starvation question reset 5
  settled; it is one more data point for the reset's rate and shape, not its cause.
- **Scripts deployed, read-only, after the reset:** [`reset6-remote-read.sh`](reset6-remote-read.sh)
  — ONE-OFF, committed here, run once over ssh under the pipeline lock; the pstore mount, copy
  and unmount that followed it used the same read-only procedure `loop.sh`'s `save_pstore` uses
  (mount read-only, copy every file byte-exact, unmount; nothing deleted).
- **Procedure:** [`batch8-baseline.sh`](batch8-baseline.sh)'s own `bench test` step (ONE-OFF,
  committed here; its bootprofile step has the PATH bug the Batch 8 section below covers, which
  is why it never ran past this step here); the `reset6-remote-read.sh` session and the pstore
  copy ran afterward, read-only, to analyze it.
- **Raw capture:** the full analysis is [`reset6-findings.md`](reset6-findings.md). Redacted
  excerpts are committed beside it: [`reset6-host-tail.log`](reset6-host-tail.log) (the capture
  markers and each stream's last line) and
  [`reset6-console-ramoops-tail.log`](reset6-console-ramoops-tail.log) (the recovered
  `console-ramoops-0`'s head and final 20 lines, 307 lines / 23555 B total, md5
  `62463305fad93d37b64e98cfeb6529e2`, MAC redacted; the full 307-line copy is not committed).
- **Verdict.** Same freeze-then-watchdog shape as resets 2, 3 and 5: `PM_RSTS` read `0x20` again
  (the fifth consecutive checked reset to do so, n = 5 of 5), a ~7.1 s silent gap before the
  ServerAlive timeout fired, and a clean recovery onto the fallback slot (`rootfs.0 (A)`,
  `BOOT_A_LEFT=3`). By mmc write-sector count the copy had reached ~92%, inside the 80-99% range
  resets 2-4 died in. This makes 4 resets in 115 default-elevator/no-diagnostics `bench test`
  runs against this checkout's HEAD (batches 1-4 plus this one), consistent with the ~2.6% rate
  already measured; it does not change any standing Finding.

### Batch 8 — soft-lockup detector

- **Owner rulings.** No SD card or PSU can be swapped on this board. More diagnostics are fine.
  The soft-lockup detector goes straight into the main image, not a diagnostic overlay, and it
  stays there as long as it does not meaningfully impact performance.
- **Hypothesis.** If the kernel is looping with interrupts on, `CONFIG_SOFTLOCKUP_DETECTOR` (with
  `CONFIG_BOOTPARAM_SOFTLOCKUP_PANIC`) panics with a stack trace, into the same `pstore` console
  this investigation already recovers, before the hardware watchdog fires. Silence under the
  detector means the freeze is either interrupts-off or a hardware hang -- the detector cannot
  see either. `CONFIG_HARDLOCKUP_DETECTOR` and `RCU_CPU_STALL_TIMEOUT` are Kconfig-infeasible on
  this board without `CONFIG_SMP` (unavailable, `CPU_V6`) or switching the preemption model
  (`CONFIG_PREEMPT_VOLUNTARY` to `CONFIG_PREEMPT`, a broader change than a diagnostic) -- out of
  scope for this batch.
- **The window this gives the detector is narrower than "6 s threshold, under the 14 s hardware
  watchdog" -- that premise is wrong as first stated, corrected here (reset 7 below exposed it).**
  The 14 s hardware-watchdog timeout runs from systemd's *last pet* (every ~6.2-7.7 s), not from
  the stop. A stop can land anywhere in that pet cycle, so the stop-to-reset window is **14 s
  minus the stop's phase in the cycle: anywhere from ~6.3 s to 14 s**, not a flat 14 s.
  `watchdog_thresh=3` (batch 8) needs 6.0-8.4 s after the stop plus print/dump time before a
  record lands -- covering only stops in roughly the first ~5 s of a pet cycle, about 70% of
  phases. A stop in the uncovered ~30% gives the detector a window as short as or shorter than
  its own latency: silence there is weak evidence, not strong. See
  [`reset7-findings.md`](reset7-findings.md) §5 for the full timing and the modelled detection
  probability (~0.3-0.7) under this batch's threshold.
- **Perf baseline, before any change.** One `bench test` on the then-current HEAD puts that
  image on bench ([`batch8-baseline.sh`](batch8-baseline.sh)'s first attempt caught reset 6,
  above; the retry, run by hand, passed clean), then `just bootprofile` three times reads the
  same image with no further change. **Raw capture:**
  [`batch8-bootprofile-3x.sh`](batch8-bootprofile-3x.sh) -- DURABLE, committed here; runs
  `bootprofile` three times under one hold of the pipeline lock. Hand-validated separately
  first: `bench.env`'s own `PATH` does not include `~/WiseBenchManager/.venv/bin`, so the
  recipe's bare `bench` call fails (`Permission denied`, exit 127) unless that directory is
  exported onto `PATH` first -- proven by running one `bootprofile` by hand with the fix and
  confirming `which bench` resolves and the run exits 0, before running the three counted below.
  Per-run figures are the analyzer's "BOOT (to 60s)" row
  (`meta-wisekiosk/recipes-core/kiosk-bootprof/README.md` covers what each column means and its
  limits):

  | run | record | wall (s) | busy% | idle% | iowait% | headroom (s) | run queue max/mean |
  |---|---|---|---|---|---|---|---|
  | 1 | `records/20261102T053659Z` | 53.5 | 73.6 | 19.98 | 6.41 | 14.06 | 14 / 2.95 |
  | 2 | `records/20261102T054014Z` | 53.5 | 74.2 | 19.57 | 6.24 | 13.82 | 15 / 3.26 |
  | 3 | `records/20261102T054329Z` | 53.5 | 68.6 | 24.92 | 6.48 | 16.77 | 17 / 3.09 |

  Mean busy% 72.1 (range 68.6-74.2), mean headroom 14.88 s (range 13.82-16.77 s). This is the
  figure the perf check after the kernel change compares against -- never pooled with it.
- **The one change.** A kernel config fragment,
  [`lockup-detect.cfg`](../../../meta-wisekiosk/recipes-kernel/linux/files/lockup-detect.cfg),
  with exactly `CONFIG_SOFTLOCKUP_DETECTOR=y` and `CONFIG_BOOTPARAM_SOFTLOCKUP_PANIC=y`, added to
  [`linux-raspberrypi_%.bbappend`](../../../meta-wisekiosk/recipes-kernel/linux/linux-raspberrypi_%.bbappend)'s
  `SRC_URI` following its own existing pattern. No sysctl.d change, no cmdline change, no other
  config. This ships: it is a change to the main image, not a diagnostic overlay. Confirmed
  host-side in the built kernel `.config` (both symbols read `=y`); device-verified below.
- **Bootstrap install.** `loop8.sh` enforces its `watchdog_thresh` step uniformly from run 1
  (below) -- that needs the new kernel already on bench, which bench's prior state (still the
  perf baseline's unmodified image) wasn't. One `bench test` on this commit, run once, outside
  `loop8.sh` and not counted as one of its runs: [`batch8-bootstrap.sh`](batch8-bootstrap.sh) --
  ONE-OFF, committed here. Passed clean (`records/20261102T064643Z`). Device-verified
  immediately after, by hand, under the lock: `kernel.watchdog_thresh` now exists (it did not on
  the pre-fragment kernel -- confirmed absent there too, with `sysctl -w` failing "unknown key");
  `kernel.soft_watchdog` reads `1`; `sysctl -w kernel.watchdog_thresh=3` succeeds and reads back
  `3`.
- **Harness:** [`loop8.sh`](loop8.sh) -- DURABLE, committed here. `loop5.sh`'s diagnostics and
  heartbeat (default `mq-deadline` scheduler, no `bfq`; default governor), `loop6.sh`/`loop7.sh`'s
  hardening (the `ERR` trap, `wait_for_board`), plus one added pre-run step, `set_lockup_thresh`:
  `sysctl -w kernel.watchdog_thresh=3` (a 6 s soft-lockup threshold -- see the window caveat
  above), with readback. **Not optional:** if the sysctl key does not exist, the detector is
  not live and the script stops -- safe to enforce from run 1 because of the bootstrap install
  above. After a reset, in addition to the pstore copy, records whether `pstore` holds a
  `dmesg-ramoops-*` file (a soft-lockup panic) or only the console record. Cap 90, stop at first
  reset.
- **Perf check, after.** Three `just bootprofile` passes on the detector kernel
  ([`batch8-bootprofile-3x.sh`](batch8-bootprofile-3x.sh), reused as-is -- the board already ran
  the detector kernel after `loop8.sh`, so no `bench test` was needed this time), same per-run
  figures as the baseline:

  | run | record | wall (s) | busy% | idle% | iowait% | headroom (s) | run queue max/mean |
  |---|---|---|---|---|---|---|---|
  | 1 | `records/20261102T081643Z` | 53.5 | 72.0 | 21.60 | 6.43 | 14.97 | 17 / 3.35 |
  | 2 | `records/20261102T081957Z` | 53.5 | 73.0 | 20.56 | 6.44 | 14.37 | 18 / 3.31 |
  | 3 | `records/20261102T082312Z` | 53.5 | 71.8 | 21.99 | 6.25 | 15.02 | 17 / 3.24 |

  Mean busy% 72.3 (range 71.8-73.0) against the baseline's 72.1 (range 68.6-74.2); mean headroom
  14.79 s (range 14.37-15.02 s) against the baseline's 14.88 s (range 13.82-16.77 s). Both are
  inside the baseline's own run-to-run spread -- reported as numbers, not a verdict on whether
  the difference is meaningful.
- **Result:** 5/5 clean, then a reset at run 6. **Raw capture:**
  [`batch8-summary.txt`](batch8-summary.txt); full per-run `metrics.py` output in
  [`batch8-metrics.txt`](batch8-metrics.txt) (run 1 shows a near-miss, `D` on
  `__ext4_find_entry` for 3.9 s, with no `wdt` dip -- noted, not analyzed further here). See
  [`reset7-findings.md`](reset7-findings.md) and the Metrics/Findings sections below.

### Batch 8, run 6 — the reset

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Image commit:** `375fd0328152583f088bf42e795ce83583e26a0a`, read from
  `records/20261102T074924Z/run.json`.
- **Scripts deployed, read-only, after the reset:** [`reset7-remote-read.sh`](reset7-remote-read.sh)
  — ONE-OFF, committed here, renamed from `remote-read.sh` to avoid colliding with batch 3's
  script already in this directory; run once over ssh under the pipeline lock.
  [`timing7.py`](timing7.py) and [`detect7.py`](detect7.py) -- each ONE-OFF, committed here.
  [`final30.py`](final30.py) -- the committed reset-5 script, reused as-is except its hardcoded
  scratch-output path, repointed at reset 7 (not a different script). Summarized in
  [`reset7-findings.md`](reset7-findings.md). Their raw outputs were unredacted and are not
  committed.
- **Procedure:** the loop's own `bench test` invocation for this run (no separate script); the
  `reset7-remote-read.sh` session and the Python reductions ran afterward, read-only, to analyze
  it.
- **Raw capture:** the full analysis is [`reset7-findings.md`](reset7-findings.md). Redacted
  excerpts are committed beside it: [`reset7-host-tail.log`](reset7-host-tail.log) (the capture
  markers and each stream's last line) and
  [`reset7-console-ramoops-tail.log`](reset7-console-ramoops-tail.log) (the recovered
  `console-ramoops-0`'s head and final 40 lines, 907 lines / 104898 B total, md5
  `0ef98d9ae6731425a416b42199327474`, MAC redacted; the full 907-line copy is not committed).
- **Verdict.** The detector was live (confirmed on the current boot: `soft_watchdog=1`,
  `softlockup_panic=1`, and `watchdog_thresh=3` was read back on the boot that reset) but did not
  fire: no `dmesg-ramoops-*`, no soft-lockup/`BUG:`/panic line in the console record, and PID1
  stayed `S do_epoll_wait` throughout (never a near-miss). The timing test says no further pet
  came after the last heartbeat, so the hardware watchdog fired the full 14 s after the last pet
  -- but the stop itself landed only ~6.5-7.7 s before that expiry (k = 1; up to 8.4 s for
  k &le; 1.08), inside the detector's own 6.0-8.4 s latency window. Modelled probability a record
  would have landed before the reset: **~0.3-0.7** -- so **this is weak evidence (likelihood
  ratio ~1.4-3.7) against an interrupts-on CPU loop, not strong evidence against one**, and it
  says nothing about an interrupts-off hang, a bus/SoC stall, or a userspace-only stall (the 10 s
  hung-task and sdhost witnesses were also cut off at ~7 s here). `PM_RSTS` read `0x20` again (6
  of 6 checked resets). By mmc write-sector count the copy had reached ~56% of the image, on
  schedule against the five healthy batch-8 runs.

### Batch 8, panic-seed proof

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Purpose.** Reset 7 left "the panic path itself is unproven on this board" as an open caveat
  -- nothing had shown the detector's `BUG:` reaching `panic()` reaching a `dmesg-ramoops` record
  on this hardware. This seeds the panic-to-pstore half directly, without the detector: it
  proves the capture path works; it does **not** prove soft-lockup detection itself.
- **Procedure:** [`sysrq-seed.sh`](sysrq-seed.sh) -- ONE-OFF, committed here, run once under the
  pipeline lock. `echo c > /proc/sysrq-trigger` on bench (`sysrq_handle_crash` -> `panic("sysrq
  triggered crash")`, bypassing the `sysrq` mask since the trigger file ignores it), wait for the
  board to come back, read the reset-cause register, mount `pstore` read-only, copy every file,
  unmount. Recoverable: a kernel panic into the same booted slot, no install in flight, nothing
  under `/boot`, a slot or the keyring touched.
- **Result: pass.** `pstore` held both `console-ramoops-0` **and `dmesg-ramoops-0`** -- the
  shipped ramoops config (`max_reason=2`) captures a panic dump, not only the console. The dmesg
  record's tail holds the crash directly: `sysrq: Trigger a crash`, `Kernel panic - not syncing:
  sysrq triggered crash`, and the call trace through `sysrq_handle_crash` -> `__handle_sysrq` ->
  `write_sysrq_trigger`. `PM_RSTS` read `0x20` -- **the same value a hardware-watchdog reset
  reads; `RSTS` cannot distinguish a panic-restart from a watchdog expiry, only the `dmesg`
  record can**, so this reading on its own proves nothing about any of the seven resets above,
  only that the capture mechanism works when a panic does happen.
- **Raw capture:** [`sysrq-seed-dmesg-ramoops.log`](sysrq-seed-dmesg-ramoops.log) -- the head
  (boot banner, kernel command line) and the crash lines, redacted (MAC scrubbed), 326 lines /
  23978 B total, md5 `e5ad0ce5a7a0fb19138a9d1ce4330bbe`; the full 326-line copy and
  `console-ramoops-0` are not committed.

### Batch 9 -- faster soft-lockup threshold

- **Hypothesis.** Reset 7 showed `watchdog_thresh=3`'s detector latency (6.0-8.4 s) racing the
  stop-to-reset window (as little as ~6.3 s at some pet-cycle phases) and losing. `watchdog_thresh=1`
  gives a 2 s soft-lockup threshold and a 0.4 s sample period, for a worst-case detection latency
  of ~3.6 s after the stop -- inside the ~6.3 s minimum window at every pet-cycle phase, with
  ~2.7 s of margin. If an interrupts-on CPU loop is the mechanism, this threshold should catch it
  reliably; continued silence under it is correspondingly stronger evidence against one than
  batch 8's was.
- **The single change from batch 8.** Only `set_lockup_thresh`'s value, `3` to `1`. Everything
  else -- diagnostics, heartbeat, scheduler, governor, hardening -- is unchanged.
- **The false-panic risk, and why the loop treats it as a stop.** On this UP board the detector's
  touch is an ordinary `SCHED_NORMAL` kworker, so CPU starvation alone -- not only a genuine
  interrupts-on loop -- can trip it at this threshold; the five clean batch-8 runs showed no
  false positive at `thresh=3` with load up to 7.8, which says nothing about `thresh=1`. A
  soft-lockup panic on an otherwise-clean install is itself data the owner needs to see, not
  noise to run past: [`loop9.sh`](loop9.sh) mounts and copies `pstore` after **every** run, not
  only a reset, and stops at `reset=yes` **or** `panic=yes` -- a false panic is captured and
  halts the loop exactly like a reset would, rather than being silently skipped and the loop
  continuing to pile more runs on top of it.
- **Harness:** [`loop9.sh`](loop9.sh) -- DURABLE, committed here. `loop8.sh` verbatim except
  `set_lockup_thresh`'s value and the panic check moving from "only on a reset" to "every run"
  (above). **Attempt 1's own `panic_recorded` had a defect** (next section); the fixed harness
  that actually ran batch 9 is [`loop9b.sh`](loop9b.sh), below.
- **Cap and stopping rule:** 90 runs, stopping at the first `reset=yes` or `panic=yes`.

### Batch 9, attempt 1 — voided by a stale-record defect, not a panic

- **What happened.** Run 1 reported `panic=yes` (`records/20261102T084317Z`), and `loop9.sh`
  stopped as designed -- but `panic_recorded` was presence-only (`ls
  $record/pstore/dmesg-ramoops-*`), with no comparison against what was already there.
  `pstore`'s ramoops records survive a warm reboot until unlinked, and this investigation never
  unlinks one, so the batch-8 panic-seed's `dmesg-ramoops-0` (above) was still on the board.
  **Confirmed:** `records/20261102T084317Z/pstore/dmesg-ramoops-0` is byte-identical (md5
  `e5ad0ce5a7a0fb19138a9d1ce4330bbe`, `cmp` clean) to the seed's own copy -- the stale record, not
  a new panic. Run 1 itself is **voided**: it is not evidence of anything about batch 9's
  hypothesis, and does not count toward any run total.
- **The fix.** [`loop9b.sh`](loop9b.sh) -- DURABLE, committed here. `loop9.sh` with
  `panic_recorded` changed from presence to a sha256 comparison against a reference manifest:
  the manifest is captured from the board once, before run 1 (so a pre-existing record like the
  seed's is in the baseline from the start), and replaced with the current run's own manifest
  after every run. `panic=yes` iff a `dmesg-ramoops-*` file is new or its sha256 changed since
  the reference -- never for a file that was already there, unchanged. `pstore` is still never
  deleted; this changes only how an already-captured record is read.
- **Validated on host files, before relaunch:** three fixtures built from the real seed record
  (an unchanged copy, a genuinely modified copy, and a run with no `dmesg-ramoops-*` file at
  all), run through the exact functions in `loop9b.sh`: unchanged -> `panic=no` (correct),
  modified -> `panic=yes` (correct), absent -> `panic=no` (correct).
- **Result:** 56/56 clean, then run 57 voided (next section) -- not a reset, not a panic.

### Batch 9, attempt 2 — 56 clean, run 57 voided by a gate refusal and a harness defect

- **What happened.** `loop9b.sh` ran 56 clean runs (`reset=no panic=no` throughout). **Raw
  capture:** [`batch9-attempt2-summary.txt`](batch9-attempt2-summary.txt) -- 56 lines, no `run=57`
  line, because run 57 crashed before reaching its own `printf` to the summary file (below).
  Run 57 (`records/20261102T180604Z`) failed inside `tests/host_suite`:
  `test_reproducibility_gate`'s
  `tools/reproducibility-gate.sh --image …` refused with `REFUSING: cannot reach origin --
  cannot prove <sha> is published`. **Confirmed by hand**, re-running the same gate against the
  same built image right after: it passed clean (`HEAD is published on origin` now succeeds) --
  the refusal was transient (a network blip reaching `origin` at that moment), not a real
  reproducibility defect, and HEAD was and still is clean and published.
  Because host_suite failed before `target_suite` ever ran, no target_suite record existed for
  this run -- and `target_suite_record`'s own `jq -e 'select(...)'` call exits `4` ("no valid
  result was ever produced"), not `1`, when nothing matches. That `4` propagated through the
  function's pipeline under `pipefail`, which `set -e` turned into `loop9b.sh` exiting outright
  (`loop9b: failed at line 187 (exit 4)`) -- a harness defect, latent since `loop.sh`, that this
  investigation had never before hit a run shaped the way run 57 was (the newest record being a
  non-`target_suite` one). **Run 57 is voided**: the transient gate refusal is why it has no
  install data; the harness crash on top of that is unrelated to batch 9's hypothesis.
- **The fix.** [`loop9c.sh`](loop9c.sh) -- DURABLE, committed here. `loop9b.sh` with
  `target_suite_record`'s `jq -e` call wrapped so a non-match ends its `&&` list at exit `0`
  instead of `4` (returning empty, not crashing), and the main loop changed to treat an empty
  record as a **voided** run rather than a fatal error: logged `voided=yes` with
  `reset=no panic=no`, and the loop continues -- it counts toward the cap, since the board and
  kernel saw a normal pre-run arm either way. Three voided runs in a row stop the loop with a
  message. Cap lowered to 34 (the remaining runs of the original 90; attempt 2's 56 clean runs
  are not repeated). Nothing else changes from `loop9b.sh`.
- **Validated before relaunch:** reproduced run 57's exact scenario (a `run.json` whose
  `command_line` is `tests/host_suite`, not `target_suite`) against both versions of
  `target_suite_record` -- `loop9b.sh`'s crashes with exit `4`, `loop9c.sh`'s returns empty
  without crashing. Simulated the main loop with a stubbed `bench`/`target_suite_record` (no
  ssh, no board): three voided runs in a row stops with the expected message; a pattern of
  voided, voided, a real record, voided, voided runs all five without stopping early and resets
  the consecutive count at the real record, as designed.
- **Result:** superseded by attempt 3, next.

### Batch 9, attempt 3 — 15 clean, run 16 voided, run 17 = reset 8

- **What happened.** `loop9c.sh` ran 15 clean runs, then run 16 was voided by the same transient
  gate refusal as attempt 2's run 57 (`records/20261102T204808Z`: `REFUSING: cannot reach
  origin`) -- confirmed the same way, and this time handled as designed: logged
  `exit=1 record=none reset=no panic=no voided=yes`, and the loop continued rather than dying.
  Run 17 caught a reset. **Raw capture:**
  [`batch9-attempt3-summary.txt`](batch9-attempt3-summary.txt); full per-run `metrics.py` output
  (runs 1-15 and 17, run 16 excluded -- it produced no record) in
  [`batch9-attempt3-metrics.txt`](batch9-attempt3-metrics.txt).
- **Run 16 left a second heartbeat running into run 17.** `arm_diagnostics` starts `hb245` before
  `bench test`; run 16's `bench test` failed inside `host_suite` without rebooting the board, so
  its heartbeat kept running when run 17's own `arm_diagnostics` started a second one on the same
  boot. The two series interleave at ~0.6 s intervals from printk ~268.6 onward in reset 8's
  `console-ramoops-0`. This is visible, not corrupting: both series write the same fields, and
  `loop9c` run 1 shows the identical doubling after `loop9b`'s run-57 crash, in an otherwise clean
  run -- so it is a side effect of a voided/crashed run leaving a boot untouched, not unique to
  this reset.
- **Result:** 15/15 clean, then a reset at run 17. See [`reset8-findings.md`](reset8-findings.md)
  and the Metrics/Findings sections below.

### Batch 9, run 17 — the reset (reset 8)

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Image commit:** `3bd3e8a9fc545ccdd6fc6ef04e04f0646634bc3a`, read from
  `records/20261102T205017Z/run.json`.
- **Scripts deployed, read-only, after the reset:**
  [`reset8-remote-read.sh`](reset8-remote-read.sh), [`reset8-remote-read2.sh`](reset8-remote-read2.sh)
  and [`reset8-remote-read3.sh`](reset8-remote-read3.sh) -- each ONE-OFF, committed here, renamed
  from `remote-read.sh`/`remote-read2.sh`/`remote-read3.sh` to avoid colliding with earlier
  resets' same-named scripts; each run once over ssh under the pipeline lock.
  [`timing8.py`](timing8.py), [`detect8.py`](detect8.py), [`latency8.py`](latency8.py),
  [`hung8.py`](hung8.py), [`episodes8.py`](episodes8.py), [`load8.py`](load8.py) and
  [`lull8.py`](lull8.py) -- each ONE-OFF, committed here. [`final30.py`](final30.py) -- the
  committed reset-5 script, reused as-is except its hardcoded scratch-output path, repointed at
  reset 8. The committed `metrics.py` and `progress.py` ran unchanged over all 16 `loop9c`
  records. Summarized in [`reset8-findings.md`](reset8-findings.md); their raw outputs were
  unredacted and are not committed.
- **Procedure:** the loop's own `bench test` invocation for this run (no separate script); the
  three `reset8-remote-read*.sh` sessions and the Python reductions ran afterward, read-only, to
  analyze it.
- **Raw capture:** the full analysis is [`reset8-findings.md`](reset8-findings.md). Redacted
  excerpts are committed beside it: [`reset8-host-tail.log`](reset8-host-tail.log) (the capture
  markers and the last heartbeat/stats data before the drop) and
  [`reset8-console-ramoops-tail.log`](reset8-console-ramoops-tail.log) (the ring-wrapped
  `console-ramoops-0`'s first surviving line and its last 40, 745 lines / 131060 B total, md5
  `6be56f5cb84a6fdb1f4b83939168b5d1`; no MAC survives in this copy -- the ring wrapped past the
  boot banner; the full 745-line copy is not committed). Its `dmesg-ramoops-0` is
  byte-identical to the batch-8 sysrq seed (`e5ad0ce5a7a0fb19138a9d1ce4330bbe`, already
  committed as [`sysrq-seed-dmesg-ramoops.log`](sysrq-seed-dmesg-ramoops.log)) -- carried over,
  not repeated here, and correctly read as `panic=no` by `loop9c`'s manifest comparison.
- **Verdict.** This stop came early in the pet cycle: the stop-to-reset window was **~11.4-13.5 s**
  (reset 5's geometry, not reset 7's), against the `watchdog_thresh=1` detector's worst-case
  3.55 s latency -- **≥7.9 s of slack, modelled P(record lands before the reset) = 1.000.**
  Nothing printed: no soft-lockup, `BUG:`, panic, oops, RCU, or SD-timeout line; no new
  `dmesg-ramoops` record. The detector was confirmed armed on the boot that reset (the 17th of 17
  `kernel.watchdog_thresh = 1` readbacks in `loop9c`'s own log, with no `FAIL`). **Rules out any
  interrupts-on kernel lockup, strongly and unconditionally** -- the detector was seeded directly
  after this reset (below) and confirmed to fire, closing the one open condition this verdict
  carried at first ("conditional on the detector actually firing, which has never been seeded on
  this board"). Two other kernel witnesses had time and were silent too: the `mmc_rescan`
  khungtaskd series (13:1
  evidence the kernel stopped scheduling it before the reports would have continued) and the SD
  driver's 10 s command timeout. `PM_RSTS` read `0x20` again (7 of 7 checked resets). By mmc
  write-sector count the copy had reached ~49%, in the middle of the 26-99% spread resets 1-8
  cover.
- **Correction to resets 5 and 7's driver attribution.** `mmc0` (the SD card) is bound to
  `sdhost-bcm2835`, i.e. `drivers/mmc/host/bcm2835.c` (`CONFIG_MMC_BCM2835=y`), confirmed on the
  board. `bcm2835-sdhost.c` -- named in `reset5-findings.md`'s own text for the 10 s per-command
  timeout -- is not built (`# CONFIG_MMC_BCM2835_SDHOST is not set`). The 10 s timeout and its
  message are the same in both files, so neither reset 5's nor reset 7's conclusions are
  affected; this only names the driver correctly. `reset5-findings.md`/`reset7-findings.md` are
  record-of-record and are not edited for this -- the correction lives here and in
  `reset8-findings.md` §3.
- **Tally, across the whole investigation.** 308 captured installs, 8 resets, 2.6% (exact 95% CI
  1.1-5.1%). Under the soft-lockup detector (batches 8-9, all attempts): 79 installs, 2 resets
  (7, 8), 2.5%. At `watchdog_thresh=1` specifically (batch 9, attempts 1-3): 73 installs, 1 reset
  (8), 1.4%. The rate has not moved across elevator, governor, detector or threshold changes.
  Zero false soft-lockup panics in those 73 `thresh=1` installs, with install-window load up to
  9.51. See [`reset8-findings.md`](reset8-findings.md) "Overall tally" for the per-scope counts
  and counting caveats.

### Soft-lockup detection seed

- **Board:** bench, Raspberry Pi Zero W. No address in this record.
- **Purpose.** Reset 8's "rules out an interrupts-on kernel lockup" verdict held only
  conditional on the soft-lockup detector actually firing -- the batch-8 sysrq seed had proved
  only panic -> pstore, never the detector itself. This seeds detection directly, owner-authorized,
  on bench, read-only except for the deliberate crash and reboot it causes.
- **Why a runtime-only method works on this kernel, without a test module.** The softlockup
  detector's touch (`softlockup_fn`, called via `stop_one_cpu_nowait`) is **not** a special
  high-priority "stop" task on this board: `include/linux/stop_machine.h`'s `!CONFIG_SMP`
  fallback (this board has no `CONFIG_SMP` -- `CPU_V6`, confirmed in the batch-8 recon) reduces
  `stop_one_cpu_nowait` to a plain `schedule_work`, an ordinary `system_wq` kworker running at
  normal `SCHED_NORMAL`/CFS priority. There is no stop-machine class to starve here -- CFS is the
  actual target. A `SCHED_FIFO` task alone is not quite enough to starve it: 6.12's fair-server
  `dl_server` independently guarantees CFS ~50 ms/s of runtime regardless of the RT group
  throttle (verified in `kernel/sched/debug.c`'s `sched_fair_server_write`, which prints "Fair
  server disabled ... system may crash due to starvation" when its runtime is set to 0 -- the
  kernel's own documentation of exactly this effect). Both the RT throttle and the fair server
  need disabling together.
- **Procedure:** [`softlockup-seed.sh`](softlockup-seed.sh) -- ONE-OFF, committed here, run once
  under the pipeline lock. Arms `kernel.watchdog_thresh=1`, `kernel.sched_rt_runtime_us=-1`
  (unlimited RT runtime) and `echo 0 > /sys/kernel/debug/sched/fair_server/cpu0/runtime` (fair
  server off), then launches `chrt -f 99 sh -c 'while true; do :; done'` backgrounded. Recoverable
  even if detection fails: the busy loop also starves PID1 (also `SCHED_NORMAL`), so systemd
  stops petting the hardware watchdog, which resets the board within its normal 14 s regardless.
- **Hand-verified before running:** `chrt`, debugfs and the `fair_server/cpu0/{runtime,period}`
  files all present on the board; `sched_rt_runtime_us` read `950000` (the 95% default) and
  `fair_server/cpu0/runtime` read `50000000` (ns, i.e. 50 ms/s) beforehand, confirming both guards
  were live before being turned off.
- **Result: pass.** A new `dmesg-ramoops-0` (md5 `b945f02fb507851245a47e7aef51ba8e`, differing
  from the sysrq seed's `e5ad0ce5a7a0fb19138a9d1ce4330bbe`) holds `watchdog: BUG: soft lockup -
  CPU#0 stuck for 3s! [sh:1375]` then `Kernel panic - not syncing: softlockup: hung tasks`, 3.58 s
  after the fair-server-disabled message -- inside the detector's own modelled 2.00-3.55 s
  worst-case latency at `thresh=1`. `PM_RSTS` read `0x20` (indistinguishable from a watchdog
  reset, as the batch-8 panic-seed's own finding already established). **The detector fires on
  this board.** This proves detection, not the specific mechanism of any of the eight resets --
  none showed a soft-lockup record themselves.
- **Raw capture:**
  [`softlockup-seed-dmesg-ramoops.log`](softlockup-seed-dmesg-ramoops.log) -- the last 39 lines
  (the fair-server warning through the panic call trace; no boot banner or MAC in this range),
  347 lines / 25543 B total, md5 `b945f02fb507851245a47e7aef51ba8e`; the full 347-line copy and
  `console-ramoops-0` are not committed.

## Configuration under test

- The capture mechanism: `tools/kiosk-install.sh`'s `stamp`/`stop_capture`, three background ssh
  streams (`dmesg -w`, `journalctl -f`, the `[stats]` busybox-sh loop) with
  `ServerAliveInterval=2`/`ServerAliveCountMax=3`, around the `rauc install` ssh call
  (`tools/kiosk-install.sh:117-128`).
- The install path under test is `just kiosk-ota`, invoked by `tests/conftest.py`'s
  `install_candidate` fixture (`tests/conftest.py:9-34`), which every `bench test` run against
  this branch exercises once per session.
- `[stats]` fields: `/proc/meminfo`'s `MemFree`/`Dirty`/`Writeback`, `/proc/loadavg`'s three
  load averages, all 17 fields of `/sys/block/mmcblk0/stat`, and `in0_lcrit_alarm` from the
  hwmon device whose `name` reads `rpi_volt` (undervoltage).
- Batches 3-5: `hb245.sh`'s heartbeat, the same fields over `/proc/uptime`/`/proc/meminfo`/
  `/proc/loadavg`/`/sys/block/mmcblk0/stat`/the same hwmon device, written to `/dev/kmsg` once a
  second so a sample survives a reset in `pstore`'s console record independent of the network;
  and the board's `hung_task_*` sysctls, raising its own kernel-side stall reporting. Batch 4
  uses `hb245-freq.sh`, which appends `scaling_cur_freq` as `freq=` and pins `scaling_governor`
  to `performance` before each run — the one variable batch 4 changes. Batch 5 uses
  `hb245-wdt.sh`, which appends `watchdog0/timeleft`, `/proc/1/stat`'s state and majflt fields,
  and `/proc/1/wchan`, all read-only; batch 5 changes no variable and stays at the `ondemand`
  baseline.

## Metrics

### Run 1

| Marker | Host time (local) | Offset from `capture started` |
|---|---|---|
| `capture started` | 00:25:52.999681-0400 | 0 s |
| `writing data to device` (journal) | 00:25:56.369121-0400 | ~3.4 s |
| both `session ended` | 00:28:11 / 00:28:12 | ~138-139 s |
| main ssh `Connection reset by peer` | between 00:28:12 and 00:33:02 (unstamped) | — |
| `capture stopped` | 00:33:02.430707-0400 | ~189 s |
| Board state after | up 9 min, idle, still on rootfs.1 (B); `BOOT_A_LEFT=0` | install to A never completed |

### Run 2

| Marker | Host time (local) | Offset from `capture started` |
|---|---|---|
| `capture started` | 11:26:22.801942-0400 | 0 s |
| `writing data to device` (journal) | 11:26:27.057221-0400 | ~4.3 s |
| `Mounting slot` (journal, live) | 11:29:48.959614-0400 | ~206.2 s |
| `capture stopped` | 11:29:49.894270-0400 | ~207.1 s |
| all three `session ended` | 11:29:49.895641 / .895809 / .895879 | ~207.1 s, after `capture stopped` |
| Board state after | Activated rootfs.0 (A), rebooted, back on A in 43 s | clean install |

No `[stats]` table for Run 1 — the stream did not exist yet. Run 2's `[stats]` lines (one
roughly every 1-1.2 s for the whole write) are in [`run2-clean.log`](run2-clean.log); nothing in
them stands out against a healthy write (`MemFree` moving in the tens of MB, `uv=0` throughout).

### Batch 2, run 14

Full detail, every raw read and the complete final-60-seconds `[stats]` dump are in
[`reset2-findings.md`](reset2-findings.md). Summary:

| Marker | Host time (local) | Offset from last `[stats]` line |
|---|---|---|
| last `[stats]` line | 21:00:22.139476-0400 | 0 s |
| `[journal] session ended` | 21:00:28.957545-0400 | 6.818 s |
| `[stats] session ended` / `[kernel] session ended` | 21:00:29.960993 / .961085-0400 | 7.822 s |
| `capture stopped` | 21:05:20.313445-0400 | 298.17 s (TCP backoff on the unmonitored install ssh) |
| next kernel start (device clock, NTP-synced) | 21:00:41.11 | ~18.1-19.0 s after the last `[stats]` line, by a separate derivation in §1 of the findings |
| warm reboot's own "Journal stopped" → kernel start, n=14 (batch 2) | — | 7.32-7.43 s |
| Board state after | booted/activated rootfs.1 (B); `BOOT_A_LEFT=0`, `BOOT_B_LEFT=3` | fell back to last-good slot |

Every `[stats]` sample in the final 60 s stayed on a steady ~1.0-1.3 s cadence (no early stop, no
burst) and the SD card was still writing at 7.5-17.3 MB/s in the last interval before the drop;
`uv` read 0 in every sample. The board did not slow down or stall before the drop — it stopped
answering everything (ssh keepalives and the stats loop alike) at the same moment, and the next
kernel did not start for at least 10.7 s after that, which is longer than this board's own warm
reset takes (7.32-7.43 s, n=14) — too long for an instant power-dip reset, and inside the 14 s
hardware-watchdog window for a freeze.

### Batch 2, run 14 — reset-cause register and pstore

The firmware's boot-time copy of the SoC's `PM_RSTS` register (`/proc/device-tree/chosen/bootloader/rsts`)
read **`0x00000020`**: bit 5 (`HADWRF`, watchdog full reset) set, bit 12 (`HADPOR`, power-on
reset) clear. A plain `reboot` and a `panic=10` restart set the same bit on this SoC, so `0x20`
alone does not separate a watchdog timeout from a deliberate reboot — but no reboot was
requested at 21:00:22 (rauc was mid-copy), and a panic/oops is ruled out next. A sag that hangs
the SoC without a power-on reset would also read `0x20`; that stays open. n = 1, no cold-boot
control sample.

`pstore` had never been mounted on this board before this read — `/proc/mounts` and
`stat -f /sys/fs/pstore` both showed it as a bare `sysfs` mountpoint, so **every earlier "pstore
empty" reading (including this record's own §4, above) looked at an unmounted directory and
could not have seen anything.** Mounted read-only, it held exactly one record,
`console-ramoops-0` (boot -1's complete kernel console, 339 lines, confirmed complete and
unwrapped) and **no `dmesg-ramoops-*`** — the zone a panic or oops would have dumped to, under
this board's `max_reason=2`/`panic_on_oops=1` configuration. The record's last line is the
identical `audit … item=6` line the live `[kernel]` stream ended on; from there to the freeze
(136 s) the kernel printed nothing at any loglevel. This board's kernel has
`CONFIG_TINY_RCU=y` and `# CONFIG_SOFTLOCKUP_DETECTOR is not set` — no RCU-stall and no
lockup detector — so a hard freeze could not have printed anything regardless; the silence is
consistent with a freeze and does not by itself distinguish one.

### Batch 3, run 35

Full detail, every raw read and the final-30-seconds `[stats]` table, is in
[`reset3-findings.md`](reset3-findings.md). Summary:

| Marker | Host/board time | Offset |
|---|---|---|
| last `[stats]` line | 03:48:18.484613-0400 host | 157.6 s after capture started |
| last `[kernel]` line (the board's own `hb245 494.87` heartbeat) | 03:48:18.825352-0400 host / board `[495.027]` | 157.96 s after capture started; the same sample is pstore's final line |
| last heartbeat due and not printed | board `[496.2]` ≈ 03:48:19.98 host | ~1.2 s after the last one |
| hung-task report due and not printed | board `[495.53]` ≈ 03:48:19.31 host | the reporter had printed every 2.076-2.081 s |
| `[journal]` / `[stats]`+`[kernel] session ended` | 03:48:25.476646 / 03:48:26.476474-0400 | 6.65 s / 7.65 s after the last `[kernel]` line |
| `capture stopped` | 03:53:16.717001-0400 | — |
| next kernel start (board, NTP-synced) | 03:48:36.162 | ≥9.4 s after the stop window (03:48:18.82-19.31) |
| Board state after | booted/activated rootfs.1 (B); `BOOT_A_LEFT=0`, `BOOT_B_LEFT=3` | fell back to last-good slot, A marked bad |

The last rauc progress line was ` 90% Copying image to rootfs.0`. Writes held 12-19 MB/s with no
slowdown; `MemFree`/`Dirty`/`Writeback` stayed in their healthy ranges; load held at 5.0; `uv`
(the firmware's sticky under-voltage bit, cleared and re-polled every 2 s) read 0 up to no more
than 2 s before the stop. The only blocked task anywhere in the boot was the routine
`mmc_rescan` kworker waiting on `__mmc_claim_host`, 18 s at the freeze — inside the healthy range
(10-79 s across 112 episodes in 34 clean runs) and the same single workqueue every healthy run
also shows. **The board-side heartbeat and the kernel's own hung-task reporter stopped within
about 0.5 s of the last line the network delivered** — the network did not die on its own while
the board stayed up; everything stopped together. `PM_RSTS` again read `0x00000020` (`HADWRF`
set, `HADPOR` clear) — a watchdog reset, not a power-on, for the second reset running.

### Batch 4, run 25

Full detail is in [`reset4-findings.md`](reset4-findings.md). Summary:

| Marker | Host/board time | Offset |
|---|---|---|
| last `[stats]` line | 08:20:35.977345-0400 host | 208.2 s after capture started |
| last `[kernel]` line (`hb245 609.02`, `freq=900000`) | 08:20:35.925704-0400 host / board `[609.136]` | same sample is pstore's final line; the host `[stats]` sample above was taken fractionally later |
| `[journal]`/`[stats]`+`[kernel] session ended` | 08:20:42.505428 / 08:20:43.505473-0400 | 6.53 s / 7.53 s after the last `[kernel]` line |
| `capture stopped` | 08:25:31.798241-0400 | — |
| next kernel start (board, NTP-synced) | 08:20:43.566 host | **7.648 s** after the last heartbeat |
| warm reboot's own "Journal stopped" → kernel start | — | 7.32-7.43 s (batch 2, n=14) plus one fresh batch-4 sample, 7.385 s (n=15) |
| Board state after | booted/activated rootfs.1 (B); `BOOT_A_LEFT=0`, `BOOT_B_LEFT=3`; governor back to `ondemand` | fell back to last-good slot, A marked bad |

Last rauc progress line: ` 99% Copying image to rootfs.0` at +204.7 s; every byte of the image
had reached the block layer (`Dirty:0`, the remaining `Writeback` accounts for the last ~0.74%).
`freq=900000` holds in every one of the 338 heartbeats, to the last line. **R (the gap between
the last heartbeat and the reset) is ≈0.26 s plus the shutdown tail — about 0.3-2.3 s — against
≥10.7 s (reset 2) and ≥9.4 s (reset 3).** A freeze-then-watchdog reset needs R ≥ 7 s (14 s
timeout, systemd pets every 7 s); this reset does not fit that shape — the board was still
running, with the heartbeat at a 1.23 s cadence and writes completing at 10-20 MB/s, until at
most ~2 s before it reset. No hung-task report was pending at the stop (unlike reset 3). `uv`
read 0 throughout, up to ≤2 s before the stop. `PM_RSTS` read `0x20` (`HADWRF` set, `HADPOR`
clear) — a watchdog reset, for the third reset running.

## Findings

- **The resets are real, not a capture artifact.** Run 1, batch 2 run 14 and batch 3 run 35 all
  show the same shape — unreachable for minutes, came back on the pre-install slot with the
  target slot never activated: *confirmed* as genuine unplanned reboots, across n = 3. All three
  fall in the last third of the slot copy under sustained ~15 MB/s SD writes (80% / 84% / 90%),
  at different elapsed times (about 131 s / 139 s / 158 s) — **across n = 3 the freeze is not at
  a fixed image offset or a fixed elapsed time**, which weakens the "same card region" idea run
  14 had left open.
- **The capture's own ordering guarantee holds.** Run 2 (clean) and batch 1's 40 clean runs all
  show `capture stopped` before any `session ended`, confirming the EXIT-trap-driven teardown
  runs before the ServerAlive-driven session closes on a healthy connection: *confirmed*.
- **Run 14's `[stats]` data rules out an instant power-dip reset and favors a freeze followed by
  the hardware watchdog.** The board stopped answering ssh and stopped emitting `[stats]` at the
  same moment — not a hang where userspace blocks but the network keeps answering — and the next
  kernel started at least 10.7 s later, longer than this board's own warm-reset time (7.32-7.43
  s, n=14). That gap falls inside the 14 s hardware-watchdog window and is too long for an
  immediate power-cycle reset. *Confirmed, moderate to strong* for ruling out an instant power
  dip. Full reasoning is in [`reset2-findings.md`](reset2-findings.md) §5 — timing only, before
  the register read below.
- **The reset-cause register and pstore confirm a watchdog reset and rule out a kernel panic,
  strongly.** `PM_RSTS` read `0x20`: `HADWRF` (watchdog full reset) set, `HADPOR` (power-on
  reset) clear. `pstore`, mounted for the first time on this board, held boot -1's complete
  console and **no `dmesg-ramoops`** — the record a panic or oops would have left under this
  image's `max_reason=2` pstore configuration. **This supersedes the "pstore empty" reading
  above (§4 of `reset2-findings.md`): that check looked at an unmounted directory and is void,
  not evidence.** Kernel panic: *ruled out, strong* (was *disfavored, moderate*). Freeze +
  hardware watchdog: *best supported* — the register and the timing agree, and nothing else on
  this board resets after a delay like that. Power dip without a power-on reset: *still
  possible*, since `PM_RSTS` cannot distinguish a sag-then-watchdog from a freeze-then-watchdog.
  See [`reset2-console-ramoops-tail.log`](reset2-console-ramoops-tail.log) for the record's own
  last lines.
- **Reset 3's network-independent heartbeat confirms the board itself stopped, strongly, and
  rules out a network-only death.** A wifi/SDIO death with the board still alive would have kept
  writing heartbeats into `pstore`'s RAM console for the 9-12 s until the watchdog reset — none
  are there. The heartbeat and the kernel's own hung-task reporter both stopped within about
  0.5 s of the last line the network delivered, so the kernel and userspace did not run on after
  the network went quiet: they stopped together. `PM_RSTS` again read `0x20` (`HADWRF` set,
  `HADPOR` clear), confirming a watchdog reset for the second time running. See
  [`reset3-findings.md`](reset3-findings.md) §§1-2 and the verdict table there.
- **Reset 4, under a pinned `performance` governor, shows DVFS is not necessary for the reset —
  strong — and does not fit the reset 2/3 shape.** `freq=900000` holds in all 338 heartbeats to
  the last line, so the CPU never left 900 MHz: one reset under a fixed frequency is enough to
  show kernel-requested frequency switching is not a required cause (firmware-side throttling
  would not show in `freq=`, so this does not cover that path). The *timing* is new and
  re-weights the field: the next kernel started only 7.648 s after the last heartbeat, against a
  measured warm-reboot time of 7.32-7.43 s (n=15) — so the reset came within about 0.3-2.3 s of
  the board still running, not after a silent gap of 7-14 s the way resets 2 and 3 did. A
  freeze-then-watchdog reset needs R ≥ 7 s to fit this board's 14 s timeout and 7 s petting
  interval; reset 4 does not fit that window. `PM_RSTS` read `0x20` again (n=3 across resets, all
  the same value). See [`reset4-findings.md`](reset4-findings.md) §4's hypothesis table.
- **PID1 starvation is refuted as the freeze-then-watchdog resets' mechanism, strong.** Reset 5
  is the first reset this investigation caught with the watchdog/PID1 heartbeat running to the
  stop, and it shows a healthy PID1 throughout: `S do_epoll_wait` in 220 of 221 heartbeats, never
  `D`, `wdt` never below the healthy floor of 7. The timing test places the board's last pet
  ~0.5 s after the last heartbeat and the watchdog's 14 s expiry lands within 0-0.1 s of the
  observed reset for a near-zero shutdown tail -- the instrument built to see a starved PID1 ran
  to the last line and did not see one. Reset 5 shares resets 2 and 3's shape (a silent gap of
  14-22 s before the next kernel starts); reset 4 does not (next kernel at only 7.648 s) and is
  not covered by this reading. See [`reset5-findings.md`](reset5-findings.md) §5.
- **What stops the board, for resets 2, 3 and 5, is still open, and this kernel build could not
  have said.** Candidates, and nothing on the board can separate them: a CPU, SoC or bus lockup
  (no softlockup or RCU-stall detector and no NMI watchdog to catch it), or a supply sag
  indistinguishable from a freeze by `PM_RSTS` alone. Either reading needs userspace and the
  kernel itself to stall wholesale with the due hung-task report going unseen (measured base rate
  ~5% in batch 4, pooled with batch 3; 0% across all 65 batch-7 windows, since `bfq` also removed
  the routine `mmc_rescan` reports batches 3-4 saw). The only blocked task at any of the five
  resets was that routine `mmc_rescan` kworker, within its own healthy range every time -- no
  precursor has been seen in 5 resets or across the healthy hung-task episodes in batches 3, 4 and
  7. `netconsole`, already shipped but unloaded, was considered and set aside: the heartbeat
  already pins the stop to ~0.5 s or less at every freeze-shaped reset. The instruments that
  would decide further — a fast external log of the board's 5 V rail, and the soft-lockup/RCU-
  stall sysctls [`reset5-findings.md`](reset5-findings.md) §5 flags as unverified on this image —
  are the owner's to arm. Reset 4's own mechanism remains separately open; this reading does not
  cover it.
- **Batch 5 run 17's near-miss and the reset are different mechanisms.** PID1 spent ~3.9 s in `D`
  on `__ext4_find_entry` -- its own filesystem read queued behind rauc's buffered bulk write --
  and `wdt` fell to 4 (healthy floor 7-8) before recovering, in an otherwise clean run: real,
  direct evidence of PID1 stalling on IO during an install. Reset 5 shows this is not what causes
  the freeze-then-watchdog reset: `bfq` removed the near-miss (0 of 85 BFQ runs dipped below
  `wdt`=7) without distinguishably changing the reset rate (1/85 against the default elevator's
  3/114, Fisher p = 0.64). See [`run17-near-miss.log`](run17-near-miss.log) and
  [`reset5-findings.md`](reset5-findings.md) §5.
- **Reset 5 is the earliest yet in the copy.** By mmc write-sector count the install had reached
  ~26% of the image, against 80/84/90/99% for resets 2-4 -- a hazard spread over the sustained-
  write window rather than a fixed phase, at n = 5 inference. `PM_RSTS` read `0x20` for the fourth
  consecutive checked reset (n = 4 of 4).
- **An interrupts-on kernel lockup is ruled out for reset 8, unconditionally.** Reset 8's own
  timing gave the `watchdog_thresh=1` detector ≥7.9 s of slack against its ≤3.55 s worst-case
  latency (modelled P = 1.000), but that ruling held only conditional on the detector actually
  firing -- never seeded on this board; the sysrq seed had proved only panic -> pstore, not
  detection. **Seeded directly:** `kernel.sched_rt_runtime_us=-1` plus disabling 6.12's fair-server
  CFS guarantee (`echo 0 > /sys/kernel/debug/sched/fair_server/cpu0/runtime`) lets a `chrt -f 99`
  busy loop starve the softlockup touch -- a plain `system_wq` (CFS) kworker on this
  non-`CONFIG_SMP` board, confirmed from `stop_one_cpu_nowait`'s `!CONFIG_SMP` fallback in
  `include/linux/stop_machine.h` (`schedule_work`, no real stop-machine class to starve; CFS is
  the actual target, and the RT throttle alone is not enough, since the fair server independently
  guarantees it runtime). The detector fired: a new `dmesg-ramoops-0` (md5 differs from the sysrq
  seed's) holds `watchdog: BUG: soft lockup - CPU#0 stuck for 3s! [sh:1375]` then `Kernel panic -
  not syncing: softlockup: hung tasks`, 3.58 s after the fair server was disabled -- consistent
  with the detector's own modelled 2.00-3.55 s latency. This closes reset 8's one open condition:
  the interrupts-on-lockup exclusion is now strong and unconditional, for that reset. See
  [`softlockup-seed-dmesg-ramoops.log`](softlockup-seed-dmesg-ramoops.log) and
  [`reset8-findings.md`](reset8-findings.md) §5's "next diagnostic" discussion, which this seed
  closes the first half of.

## Other board activity on this board

Ticket #245's own P2 and P4 proofs (the capture surviving `dmesg` failing, and the capture
stopping cleanly when the install itself is killed) ran on this same board, between batch 2 and
the reset-cause register read. Both are proofs of the capture mechanism, not part of this
reset's own diagnosis, but are noted here for completeness since they touched the board:

- P2 passed: `[kernel] session ended` arrived immediately (the seeded failure), a live
  `Mounting slot` line arrived, exit 0, slot activated.
- A first P4 attempt is **void**. Its script released the pipeline lock (`flock -o <lock> -c
  '...'`, which runs the wrapped command under `$SHELL` — zsh on this host, which has no
  `$EPOCHREALTIME` without `zmodload`) as soon as that script errored, before the kill was sent,
  while `tools/kiosk-install.sh` and its ssh children kept running, unprotected, in the
  background. The install completed on its own (success, no reboot — `kiosk-install.sh` never
  reboots); its exit status was never captured and is not inferred. No harm resulted: the board
  was not rebooted, and P3's checks (no stray host processes, lock free, no board-side leftover)
  came back clean once it finished.
- A second, fixed P4 attempt passed cleanly: run entirely under plain `bash` (`flock -o <lock>
  bash <script>`, no `$SHELL`-spawning `flock -c`), with the script waiting on
  `tools/kiosk-install.sh` before returning so the lock cannot release while it or its ssh
  children are alive. Exit status 255 (OpenSSH's own status on `SIGTERM` mid-session), `==
  after` absent from its log, `capture stopped` present.

## Changes configured as a result

**No change — capture judged sufficient; investigation stays open on cause.**
`tools/kiosk-install.sh`'s capture (kernel/journal/`[stats]`) ships as this ticket's PR #295 and
needs no further instrument change: run 14 shows it carries enough signal (timing against the
board's own warm-reset time) to discriminate a freeze-then-watchdog reset from an instant
power-dip reset, which was the open question after run 1. What froze the board is not decided by
this record and is left as follow-up work, not a blocker on this ticket's capture.
