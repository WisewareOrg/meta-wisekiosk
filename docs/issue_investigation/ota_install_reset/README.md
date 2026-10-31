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
| Batch 5 | bench · Pi Zero W | this branch's HEAD at launch | `loop5.sh` — durable | Observation: watchdog `timeleft` and PID1 state added to the heartbeat, no variable changed (baseline `ondemand`), cap 90 runs; pending |

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

### Batch 5 — watchdog and PID1 observation (pending)

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
- **Result:** pending. This section updates once the loop produces a reset or exhausts its cap.

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
- **What froze the board is still open, and this kernel build could not have said.** Resets 2
  and 3 fit a freeze followed by the hardware watchdog; reset 4 does not — it looks like the
  watchdog fired while the board was still live. Candidates, and nothing on the board can
  separate them: a CPU, SoC or bus lockup (no softlockup or RCU-stall detector and no NMI
  watchdog to catch it) for resets 2/3; for reset 4, either the watchdog firing because PID1
  itself stopped petting it for ≥14 s while the rest of the kernel, the heartbeat and I/O ran on
  (page-in and dirty-throttle waits are killable and invisible to the hung-task reporter, so a
  stalled PID1 would not show there either), or a supply sag that resets the SoC directly (RSTS
  cannot distinguish the two, and reset 2's timing argument against an immediate dip does not
  apply to reset 4). Either resets 2-4 are two different modes, or one mechanism — the watchdog
  on a stalled PID1, or supply — covers all three, which for resets 2/3 needs userspace to stall
  wholesale and the due hung-task report to go unseen (measured base rate ~5% in batch 4, pooled
  with batch 3). This is open, and is the owner's call to weigh. The only blocked task at any of
  the four resets was the routine `mmc_rescan` kworker, within its own healthy range every time —
  no precursor has been seen in 4 resets or across the healthy hung-task episodes in batches 3-4.
  `netconsole`, already shipped but unloaded, was considered and set aside: the heartbeat already
  pins the stop to ~0.5 s (reset 3) or less (reset 4). The instruments that would decide further
  — a fast external log of the board's 5 V rail, and `watchdog0/timeleft` plus PID1's own state
  added to the heartbeat — are host-side and read-only respectively; the owner's to say on the
  former; the latter is tracked as follow-up.

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
