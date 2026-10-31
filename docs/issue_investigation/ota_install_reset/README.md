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
| Batch 4 | bench · Pi Zero W | this branch's HEAD at launch | `loop4.sh` — durable | Experiment: `performance` governor (fixed frequency), cap 90 runs; pending |

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

### Batch 4 — fixed-frequency experiment (pending)

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
- Batches 3 and 4: `hb245.sh`'s heartbeat, the same fields over `/proc/uptime`/`/proc/meminfo`/
  `/proc/loadavg`/`/sys/block/mmcblk0/stat`/the same hwmon device, written to `/dev/kmsg` once a
  second so a sample survives a reset in `pstore`'s console record independent of the network;
  and the board's `hung_task_*` sysctls, raising its own kernel-side stall reporting. Batch 4
  uses `hb245-freq.sh`, which appends `scaling_cur_freq` as `freq=` and pins `scaling_governor`
  to `performance` before each run — the one variable batch 4 changes.

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
- **What froze the board is still open, and this kernel build could not have said.** Two
  candidates remain, and nothing on the board can separate them: a CPU, SoC or bus lockup (for
  example an SD-host or SDIO access that never completes and stalls the single ARMv6 core, with
  no softlockup or RCU-stall detector and no NMI watchdog to catch it), or a supply sag deep
  enough to hang the SoC without a power-on reset (the firmware's sticky under-voltage bit covers
  up to ~2 s before the stop, not the stop itself). The only blocked task at any of the three
  resets was the routine `mmc_rescan` kworker, within its own healthy range every time — no
  precursor has been seen in 3 resets or 112 healthy hung-task episodes. `netconsole`, already
  shipped but unloaded, was considered and set aside: the heartbeat already pins the stop to
  ~0.5 s, and the single remaining instrument that could decide CPU/bus-lockup against supply sag
  is a fast (millisecond-resolution) external log of the board's 5 V input across a reset — not
  achievable in-band, and the owner's to say whether the bench has one.

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
