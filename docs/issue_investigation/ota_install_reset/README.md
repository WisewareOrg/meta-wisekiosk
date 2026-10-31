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

## Findings

- **The resets are real, not a capture artifact.** Run 1's board was unreachable for ~4.5
  minutes (both monitoring sessions down, the install ssh itself eventually reset) and came
  back up on its pre-install slot with the target slot never activated. Batch 2 run 14 shows the
  same shape with `[stats]` data to read: *confirmed* as genuine unplanned reboots, in both
  cases during the slot copy (run 1 at image offsets 80-84%; run 14's drop falls in the same
  phase). With n = 2 this cannot tell "the same image offset" apart from "the same elapsed
  time."
- **The capture's own ordering guarantee holds.** Run 2 (clean) and batch 1's 40 clean runs all
  show `capture stopped` before any `session ended`, confirming the EXIT-trap-driven teardown
  runs before the ServerAlive-driven session closes on a healthy connection: *confirmed*.
- **Run 14's `[stats]` data rules out an instant power-dip reset and favors a freeze followed by
  the hardware watchdog.** The board stopped answering ssh and stopped emitting `[stats]` at the
  same moment — not a hang where userspace blocks but the network keeps answering — and the next
  kernel started at least 10.7 s later, longer than this board's own warm-reset time (7.32-7.43
  s, n=14). That gap falls inside the 14 s hardware-watchdog window and is too long for an
  immediate power-cycle reset. *Confirmed, moderate to strong* for ruling out an instant power
  dip; *best supported, moderate to strong* for a freeze-then-watchdog reset; a kernel panic is
  *disfavored* (pstore was empty). Full reasoning, including the two hypotheses not favored, is
  in [`reset2-findings.md`](reset2-findings.md) §5.
- **What froze the board is still open.** Candidates are a CPU/kernel lockup with interrupts
  off, a wedged SD-host or SDIO bus, or a voltage sag deep enough to hang the SoC without
  tripping `uv` at 1 Hz resolution. Nothing in the capture shows a cause — no console line, no
  counter trend — only that everything stopped at once. Deciding watchdog-vs-outage needs the
  SoC's own reset-cause register (`PM_RSTS`, not exposed by this board's `bootstatus`), which
  this investigation did not read (a `/dev/mem` read was judged too risky for a read-only
  check). `netconsole`, already shipped but unloaded, is named in `reset2-findings.md` as the
  instrument that would catch what froze it.

## Changes configured as a result

**No change — capture judged sufficient; investigation stays open on cause.**
`tools/kiosk-install.sh`'s capture (kernel/journal/`[stats]`) ships as this ticket's PR #295 and
needs no further instrument change: run 14 shows it carries enough signal (timing against the
board's own warm-reset time) to discriminate a freeze-then-watchdog reset from an instant
power-dip reset, which was the open question after run 1. What froze the board is not decided by
this record and is left as follow-up work, not a blocker on this ticket's capture.
