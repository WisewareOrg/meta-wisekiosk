# What causes the bench board's hard reset mid-`rauc install`, and can the capture explain it?

| | |
|---|---|
| **Issue** | #245 Capture the board's logs during every image update |
| **Status** | open |
| **Opened / concluded** | 2026-10-30 / |

The bench board has hard-reset mid-`rauc install` about 3 times in 44 installs, with nothing
surviving the reset to say why (its journal is on the same SD card). `tools/kiosk-install.sh`
streams the board's kernel log, journal and once-a-second memory/load/SD/undervoltage stats to
the console across the install. Run 1 caught a real reset with the first two streams
but no stats, so there was nothing to judge the cause from. Run 2, after the `[stats]` stream
was added, passed clean and confirmed the capture's own ordering guarantee holds on a healthy
install. Open: a loop (`loop.sh`) repeats `bench test` on this branch's head until an install
resets the board (capped at 40 runs), so the next reset has `[stats]` data to read.

## Test runs

| Run | Board (role) | Image commit | Harness / scripts | Result (1 line) |
|---|---|---|---|---|
| 1 | bench · Pi Zero W | `fee57a946f4b256d1cd3999daf83a6b048f5fcbb` | `run-bench-test.sh` — one-off | Real mid-write reset; no `[stats]` stream yet |
| 2 | bench · Pi Zero W | `b6d537714dfc5efd85c2a80c88bfe44313f70cdd` | `run-bench-test.sh` — one-off | Clean install; capture ordering holds, `[stats]` lines land ~1/s |

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

### Run 3+ — the loop

- **Harness:** [`loop.sh`](loop.sh) — DURABLE to this investigation, committed here. Runs
  `bench test <sha>` up to 40 times from `~/meta-wisekiosk`, under one hold of the pipeline
  lock for the whole loop, restoring the branch between runs. Appends one line per run to a
  summary file: `<host-ts> run=<i> sha=<sha> exit=<status> record=<records/<ts> dir> reset=<yes|no>`,
  and stops at the first `reset=yes`. Per-run detail (the full `report.jsonl`, `bench.log`)
  lives under that run's own `records/<ts>/` directory, not duplicated here.
- **Reset detection:** a run is `reset=yes` iff its `target_suite` record's install item shows a
  capture `session ended` line before its `capture stopped` line — the ordering
  `tools/kiosk-install.sh` guarantees on a clean run (Run 2) and that Run 1 violated. Checked
  against both known runs before trusting it in the loop (Run 1 → yes, Run 2 → no).
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

## Findings

- **The reset is real, not a capture artifact.** Run 1's board was unreachable for ~4.5 minutes
  (both monitoring sessions down, the install ssh itself eventually reset) and came back up on
  its pre-install slot with the target slot never activated — a genuine unplanned reboot during
  the write, not a false keepalive timeout: *open*, cause not yet identified.
- **The capture's own ordering guarantee holds.** Run 2 shows `capture stopped` before any
  `session ended`, confirming the EXIT-trap-driven teardown runs before the ServerAlive-driven
  session closes on a healthy connection: *confirmed*.
- **No stats data yet for an actual reset.** Run 1 predates the `[stats]` stream; Run 2 has
  `[stats]` but no reset. Whether the reset correlates with memory pressure, SD throughput,
  load, or undervoltage is *open*, pending a reset caught by the loop.

## Changes configured as a result

Not yet — open. `tools/kiosk-install.sh`'s capture (including `[stats]`) already ships
(PR #295); what remains open here is the *cause* of the reset, which the loop in
[`loop.sh`](loop.sh) is run to catch with judgeable data. This section is updated once that
loop produces a reset or exhausts its 40-run cap.
