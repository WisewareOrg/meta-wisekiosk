# Reset 3 analysis: batch-3 loop run 35 (#245 mid-install hard reset)

Bench board only, and read-only. I changed nothing on the board: no reboot, no install, no mount,
no /boot write, no pstore file touched. Prod was not contacted. `~/meta-wisekiosk`'s git state was
not touched. There were two board sessions, each a single
`flock -o -w 900 ~/wisekiosk-bench/records/lock ssh <tools/kiosk-install.sh options> <bench> sh -s < script`,
and the lock was free both times. Addresses, the hostname, the MAC and the machine-id are written as
`<addr>`, `<host>`, `<mac>` and `<machine-id>` below.

- **Record:** `records/20261031T074356Z`, sha `a4e94247dc2a`. The loop summary line is
  `2026-10-31T03:53:20-0400 run=35 sha=a4e94247dc2a82b681d2eb4c6307dbb31efa54e5 exit=2 record=records/20261031T074356Z reset=yes`.
  This is the first reset in 35 batch-3 runs; runs 1–34 were clean.
- **pstore copy:** `records/20261031T074356Z/pstore/console-ramoops-0`, 91 236 B, 861 lines,
  md5 `5a575b6fc3ef10b5b90b0f49ba637f0f`. It is the only file. Its kernel command line carries the
  MAC, so it must be scrubbed before it goes anywhere tracked.
- **Scripts:** committed beside this file.
  - `extract.py` pulls the install item's captured setup sections into `stdout.txt` and
    `stderr.txt`.
  - `window.py` gives the final 30 s of `[stats]` and the cadence.
  - `batch3.py` compares all 35 batch-3 runs.
  - `episodes.py` measures the healthy hung-task episode lengths.
  - `remote-read.sh` and `remote-read2.sh` are the board reads, run via `run-read.sh` (the same
    flock+ssh pattern for both; `remote-read2.sh`'s session substitutes it for `remote-read.sh`).
    Their raw outputs were unredacted and are not committed; the redacted excerpts are
    `reset3-host-tail.log` and `reset3-console-ramoops-tail.log`.
- **Clocks.** Timestamps are **host** time (`-0400`) unless marked *board*. Bracketed `[ 495.027]`
  values are boot −1's printk clock.
  - Board printk 495.027273 is board wall time 03:48:18.805110. That is the `dmesg --time-format iso`
    stamp on the same line in the `[kernel]` stream, and the host received that line at
    03:48:18.825352.
  - So **host ≈ board wall + ~0.02 s**, and boot −1's kernel started at board wall 03:40:03.778.

## Verdict

**The whole system froze again. The network did not die on its own.** The board-side heartbeat
needs no network and writes into RAM that survives the reset. Its last line in the pstore console
is `hb245 494.87`, at `[495.027]` ≈ **03:48:18.81** host. That is the **same line** the host
received last, at 03:48:18.825.

- After that line the kernel printed **nothing** in the ~17 s before the next kernel started:
  - no further heartbeat,
  - no hung-task report,
  - no oops, and no mmc, sdhost, brcmfmac, RCU, OOM or under-voltage line.
- The kernel's hung-task reporter had been printing every 2.08 s, and its next report was due at
  about [495.53]. It **did not appear**.
- So the kernel and userspace stopped within about **0.5 s** of the last line the network
  delivered, and did **not** run on after the network went silent.
- About 9.4–12 s later the hardware watchdog reset the board:
  - **RSTS = 0x00000020** (HADWRF, the watchdog full reset), with no HADPOR (power-on reset).
  - The new kernel started at **03:48:36.162**.

This matches reset 2 in every respect that was measured: the streams stopped together, there was
no panic, RSTS was 0x20, and the reset came 9–14 s after the freeze. What is new is
network-independent proof that the board itself stopped.

**What froze is still not named.** The last 30 s show no precursor:
- Writes ran at a steady 12–19 MB/s.
- Dirty, Writeback and MemFree were steady, and load was 5.0.
- The firmware's sticky under-voltage bit read 0 to the end.
- The only blocked task was the routine `mmc_rescan` kworker waiting in `__mmc_claim_host`. That
  is the same pattern as in every healthy batch-3 run, and it had been blocked 18 s, against a
  healthy range of 10–79 s.

This kernel has no lockup or RCU stall detector, so a CPU or bus stall with timers stopped prints
nothing. The silence is what such a stall would leave, and it is also what a supply sag that hangs
the SoC without a power-on reset would leave.

| claim | strength |
|---|---|
| Network-only death (wifi/SDIO died, board alive) | **Ruled out, strong** (§2) |
| Whole-system stop within ~0.5 s of the last delivered line | **Strong** that both the heartbeat and khungtaskd stopped. The 0.5 s bound is **moderate**: it rests on khungtaskd's next report being due. In healthy runs 1 of 59 episodes ended at 18 s |
| A live kernel with the I/O path wedged (tasks stuck, scheduler running) | **Disfavoured, moderate to strong.** It predicts more reports for pid 1967 at ~[495.5], [497.6], [499.7] and so on, and more heartbeats. None appeared |
| Watchdog reset, not power-on | **Strong** for this boot's register. Decode as in `reset2-rsts-pstore.md` §1; still no cold-boot control |
| CPU or bus lockup vs supply sag without POR | **Open.** Nothing on the board can separate them (§4) |

## 1. Host-side timeline

Capture markers (stderr):

    2026-10-31T03:45:40.869220-0400 capture started
    2026-10-31T03:48:25.476646-0400 [journal] session ended
    2026-10-31T03:48:26.476474-0400 [stats] session ended
    2026-10-31T03:48:26.476543-0400 [kernel] session ended
    Read from remote host <addr>: Connection reset by peer        (unstamped: the rauc-install ssh)
    client_loop: send disconnect: Broken pipe                    (unstamped)
    2026-10-31T03:53:16.717001-0400 capture stopped
    error: recipe `kiosk-install` failed on line 235 with exit code 255

The last line of each stream (stdout):

    2026-10-31T03:48:17.667697-0400 [journal] 2026-10-31T03:48:17.237631-04:00 <host> kernel: 5fe0: 00000000 00000000 00000000 00000000 00000013 00000000
    2026-10-31T03:48:18.088444-0400 [journal] 2026-10-31T03:48:17.628085-04:00 <host> unknown: hb245 493.66 MemFree:46656 Dirty:8468 Writeback:36652 load=5.03 2.99 1.35 mmc=5195 626 634830 118142 4957 428176 3650228 7997684 0 125690 8115827 0 0 0 0 0 0 uv=0   (LAST real [journal] line)
    2026-10-31T03:48:18.484613-0400 [stats] MemFree:48828 Dirty:11812 Writeback:37744 load=5.03 2.99 1.35 mmc=5195 626 634830 118142 4977 432240 3670708 8051193 0 126370 8169336 0 0 0 0 0 0 uv=0   (LAST [stats] line)
    2026-10-31T03:48:18.825352-0400 [kernel] 2026-10-31T03:48:18,805110-04:00 hb245 494.87 MemFree:47116 Dirty:8300 Writeback:37168 load=5.03 2.99 1.35 mmc=5195 626 634830 118142 4988 432240 3681972 8079335 0 126710 8197477 0 0 0 0 0 0 uv=0   (LAST real [kernel] line)
    2026-10-31T03:48:25.475971-0400 [journal] Timeout, server <addr> not responding.
    2026-10-31T03:48:26.475930-0400 [kernel] Timeout, server <addr> not responding.
    2026-10-31T03:48:26.475930-0400 [stats] Timeout, server <addr> not responding.

- The last rauc progress line was ` 90% Copying image to rootfs.0`.
- The last sign of life came **157.6 s** (`[stats]`) and **157.96 s** (`[kernel]`) after capture
  start.
- The sessions dropped 6.65 s and 7.65 s after the last `[kernel]` line. That fits
  `ServerAliveInterval=2 ServerAliveCountMax=3`, with the same 1 s split between sessions as reset 2.

**Cadence.**
- `[stats]`: 127 samples, mean interval 1.23 s.
- The only gap over 1.6 s is **8.78 s at +5 s** (03:45:45.90 → 03:45:54.69), at install start.
  The heartbeat shows the same stall: `[341.494] hb245 341.21` then `[350.898] hb245 345.57`.
  - In that second line the shell read uptime 5.3 s before its write reached kmsg.
  - This is the routine install-start stall. 21 of the 34 healthy batch-3 runs have a `[stats]`
    gap of 3.1–7.5 s at +6–9 s (`batch3.py`).
  - 8.8 s is the largest of the 35 runs. It is 1.3 s above the healthy maximum and 2.5 min before
    the freeze, so I read it as unremarkable, with weak confidence.
- After that there is no gap over 1.6 s right up to the end.

**The last 30 s of `[stats]`** (`window.py`). Columns are MemFree, Dirty and Writeback in kB, the
1-min load, then write sectors since boot and the write rate between samples. `in_flight` is 0 in
every sample, healthy runs included, so it carries no information.

| host time | MemFree | Dirty | WB | load1 | wsect | MB/s | uv |
|---|---|---|---|---|---|---|---|
| 03:47:49.239 | 74280 | 12232 | 19456 | 5.15 | 2828884 | | 0 |
| 03:47:50.436 | 58696 | 23380 | 1024 | 5.14 | 2866772 | 16.2 | 0 |
| 03:47:51.610 | 57120 | 44544 | 1028 | 5.14 | 2892892 | 11.4 | 0 |
| 03:47:52.733 | 46100 | 39636 | 6212 | 5.14 | 2927708 | 15.9 | 0 |
| 03:47:53.885 | 48536 | 45288 | 1028 | 5.14 | 2962652 | 15.5 | 0 |
| 03:47:55.043 | 48036 | 45716 | 1028 | 5.05 | 2993524 | 13.7 | 0 |
| 03:47:56.372 | 49372 | 40856 | 7748 | 5.05 | 3024244 | 11.8 | 0 |
| 03:47:57.272 | 49740 | 8892 | 36928 | 5.05 | 3059212 | 19.9 | 0 |
| 03:47:58.401 | 47432 | 8112 | 37444 | 5.05 | 3089932 | 13.9 | 0 |
| 03:47:59.508 | 46424 | 8368 | 37964 | 5.05 | 3122700 | 15.2 | 0 |
| 03:48:00.735 | 47132 | 9552 | 35412 | 5.04 | 3160588 | 15.8 | 0 |
| 03:48:01.921 | 55704 | 10432 | 39660 | 5.04 | 3193356 | 14.2 | 0 |
| 03:48:03.047 | 50668 | 10440 | 35336 | 5.04 | 3226348 | 15.0 | 0 |
| 03:48:04.231 | 46012 | 4732 | 42064 | 5.04 | 3260140 | 14.6 | 0 |
| 03:48:05.455 | 46044 | 10572 | 33880 | 5.12 | 3295980 | 15.0 | 0 |
| 03:48:06.588 | 46068 | 11880 | 34396 | 5.12 | 3326700 | 13.9 | 0 |
| 03:48:07.731 | 49340 | 12132 | 17500 | 5.12 | 3358444 | 14.2 | 0 |
| 03:48:08.965 | 48700 | 15368 | 25176 | 5.12 | 3395532 | 15.4 | 0 |
| 03:48:10.272 | 47860 | 12144 | 38532 | 5.03 | 3427276 | 12.4 | 0 |
| 03:48:11.500 | 50704 | 9460 | 40688 | 5.03 | 3463292 | 15.0 | 0 |
| 03:48:12.729 | 48080 | 7624 | 37624 | 5.03 | 3501180 | 15.8 | 0 |
| 03:48:13.900 | 47100 | 9088 | 36096 | 5.03 | 3537020 | 15.7 | 0 |
| 03:48:15.046 | 45132 | 10216 | 35584 | 5.03 | 3570812 | 15.1 | 0 |
| 03:48:16.370 | 45212 | 11336 | 34560 | 5.03 | 3603580 | 12.7 | 0 |
| 03:48:17.336 | 48320 | 11140 | 34048 | 5.03 | 3639988 | 19.3 | 0 |
| 03:48:18.485 | 48828 | 11812 | 37744 | 5.03 | 3670708 | 13.7 | 0 |

The write path was moving at full rate right up to the last sample. Nothing slowed, dirty pages
did not pile up, and memory did not fall away.

## 2. The pstore console record

**Which boot this is.**
- The record starts `[    0.000000] Booting Linux on physical CPU 0x0` and is 861 lines, far
  below the 128 KiB console zone, so it did not wrap.
- It carries this install's audit serial, `audit(1793432743.985:34)` at `[340.228]`, the rauc
  `installer` verity mount.
- The host `[kernel]` stream and the record hold **the same 306 heartbeats and the same 12
  hung-task reports**. None is in one and not the other (`hb-host.txt` / `hb-pstore.txt`). The
  network stream lost nothing, and the record holds nothing the network did not deliver.

**Its last 80 lines, verbatim** (nothing identifying in this range):

```
[  486.440267] hb245 486.19 MemFree:46744 Dirty:8320 Writeback:41100 load=5.03 2.95 1.33 mmc=5195 626 634830 118142 4697 401715 3428300 7256943 0 119290 7375085 0 0 0 0 0 0 uv=0
[  487.209761] INFO: task kworker/0:1:1967 blocked for more than 12 seconds.
[  487.209865]       Not tainted 6.12.93 #1
[  487.209897] "echo 0 > /proc/sys/kernel/hung_task_timeout_secs" disables this message.
[  487.209927] task:kworker/0:1     state:D stack:0     pid:1967  tgid:1967  ppid:2      flags:0x00200000
[  487.209988] Workqueue: events_freezable mmc_rescan
[  487.210054] Call trace: 
[  487.210075]  __schedule from schedule+0x28/0x138
[  487.210176]  schedule from __mmc_claim_host+0xdc/0x1d4
[  487.210239]  __mmc_claim_host from mmc_sd_detect+0x1c/0x74
[  487.210308]  mmc_sd_detect from mmc_rescan+0xa8/0x354
[  487.210363]  mmc_rescan from process_one_work+0x134/0x340
[  487.210431]  process_one_work from worker_thread+0x168/0x2f0
[  487.210492]  worker_thread from kthread+0xc4/0xe4
[  487.210558]  kthread from ret_from_fork+0x14/0x28
[  487.210609] Exception stack(0xdcc15fb0 to 0xdcc15ff8)
[  487.210650] 5fa0:                                     00000000 00000000 00000000 00000000
[  487.210693] 5fc0: 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000
[  487.210733] 5fe0: 00000000 00000000 00000000 00000000 00000013 00000000
[  487.741326] hb245 487.46 MemFree:49340 Dirty:5320 Writeback:39664 load=5.03 2.95 1.33 mmc=5195 626 634830 118142 4746 405797 3463292 7357876 0 120420 7476019 0 0 0 0 0 0 uv=0
[  489.001369] hb245 488.75 MemFree:50148 Dirty:9024 Writeback:35576 load=5.03 2.95 1.33 mmc=5195 626 634830 118142 4786 409862 3504252 7460708 0 121600 7578850 0 0 0 0 0 0 uv=0
[  489.289676] INFO: task kworker/0:1:1967 blocked for more than 14 seconds.
[  489.289774]       Not tainted 6.12.93 #1
[  489.289807] "echo 0 > /proc/sys/kernel/hung_task_timeout_secs" disables this message.
[  489.289835] task:kworker/0:1     state:D stack:0     pid:1967  tgid:1967  ppid:2      flags:0x00200000
[  489.289900] Workqueue: events_freezable mmc_rescan
[  489.289967] Call trace: 
[  489.289987]  __schedule from schedule+0x28/0x138
[  489.290089]  schedule from __mmc_claim_host+0xdc/0x1d4
[  489.290148]  __mmc_claim_host from mmc_sd_detect+0x1c/0x74
[  489.290221]  mmc_sd_detect from mmc_rescan+0xa8/0x354
[  489.290273]  mmc_rescan from process_one_work+0x134/0x340
[  489.290344]  process_one_work from worker_thread+0x168/0x2f0
[  489.290408]  worker_thread from kthread+0xc4/0xe4
[  489.290473]  kthread from ret_from_fork+0x14/0x28
[  489.290525] Exception stack(0xdcc15fb0 to 0xdcc15ff8)
[  489.290565] 5fa0:                                     00000000 00000000 00000000 00000000
[  489.290666] 5fc0: 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000
[  489.290715] 5fe0: 00000000 00000000 00000000 00000000 00000013 00000000
[  490.237777] hb245 490.01 MemFree:47716 Dirty:10740 Writeback:34048 load=5.03 2.95 1.33 mmc=5195 626 634830 118142 4822 413936 3541116 7553379 0 122660 7671522 0 0 0 0 0 0 uv=0
[  491.371138] INFO: task kworker/0:1:1967 blocked for more than 16 seconds.
[  491.371234]       Not tainted 6.12.93 #1
[  491.371264] "echo 0 > /proc/sys/kernel/hung_task_timeout_secs" disables this message.
[  491.371293] task:kworker/0:1     state:D stack:0     pid:1967  tgid:1967  ppid:2      flags:0x00200000
[  491.371350] Workqueue: events_freezable mmc_rescan
[  491.371411] Call trace: 
[  491.371430]  __schedule from schedule+0x28/0x138
[  491.371521]  schedule from __mmc_claim_host+0xdc/0x1d4
[  491.371576]  __mmc_claim_host from mmc_sd_detect+0x1c/0x74
[  491.371639]  mmc_sd_detect from mmc_rescan+0xa8/0x354
[  491.371693]  mmc_rescan from process_one_work+0x134/0x340
[  491.371760]  process_one_work from worker_thread+0x168/0x2f0
[  491.371815]  worker_thread from kthread+0xc4/0xe4
[  491.371876]  kthread from ret_from_fork+0x14/0x28
[  491.371924] Exception stack(0xdcc15fb0 to 0xdcc15ff8)
[  491.371958] 5fa0:                                     00000000 00000000 00000000 00000000
[  491.371993] 5fc0: 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000
[  491.372026] 5fe0: 00000000 00000000 00000000 00000000 00000013 00000000
[  491.450377] hb245 491.25 MemFree:56920 Dirty:8688 Writeback:37796 load=5.03 2.99 1.35 mmc=5195 626 634830 118142 4856 420032 3575932 7637451 0 123600 7755594 0 0 0 0 0 0 uv=0
[  492.660645] hb245 492.45 MemFree:49992 Dirty:6052 Writeback:40532 load=5.03 2.99 1.35 mmc=5195 626 634830 118142 4917 424096 3609268 7896405 0 124620 8014547 0 0 0 0 0 0 uv=0
[  493.449802] INFO: task kworker/0:1:1967 blocked for more than 18 seconds.
[  493.449901]       Not tainted 6.12.93 #1
[  493.449931] "echo 0 > /proc/sys/kernel/hung_task_timeout_secs" disables this message.
[  493.449957] task:kworker/0:1     state:D stack:0     pid:1967  tgid:1967  ppid:2      flags:0x00200000
[  493.450018] Workqueue: events_freezable mmc_rescan
[  493.450079] Call trace: 
[  493.450098]  __schedule from schedule+0x28/0x138
[  493.450189]  schedule from __mmc_claim_host+0xdc/0x1d4
[  493.450256]  __mmc_claim_host from mmc_sd_detect+0x1c/0x74
[  493.450315]  mmc_sd_detect from mmc_rescan+0xa8/0x354
[  493.450362]  mmc_rescan from process_one_work+0x134/0x340
[  493.450419]  process_one_work from worker_thread+0x168/0x2f0
[  493.450495]  worker_thread from kthread+0xc4/0xe4
[  493.450547]  kthread from ret_from_fork+0x14/0x28
[  493.450590] Exception stack(0xdcc15fb0 to 0xdcc15ff8)
[  493.450620] 5fa0:                                     00000000 00000000 00000000 00000000
[  493.450653] 5fc0: 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000
[  493.450683] 5fe0: 00000000 00000000 00000000 00000000 00000013 00000000
[  493.847946] hb245 493.66 MemFree:46656 Dirty:8468 Writeback:36652 load=5.03 2.99 1.35 mmc=5195 626 634830 118142 4957 428176 3650228 7997684 0 125690 8115827 0 0 0 0 0 0 uv=0
[  495.027273] hb245 494.87 MemFree:47116 Dirty:8300 Writeback:37168 load=5.03 2.99 1.35 mmc=5195 626 634830 118142 4988 432240 3681972 8079335 0 126710 8197477 0 0 0 0 0 0 uv=0
```

**The last heartbeat vs the last line the host received.**
- The last heartbeat is `[  495.027273] hb245 494.87 …`.
  - That is board wall 03:48:18.805, which is **≈ 03:48:18.81–18.83 host**.
  - It is **the record's final line**.
- The host's last `[kernel]` line is the same line, received at 03:48:18.825. The host's last
  `[stats]` line came 0.34 s earlier.
- **So the kernel and userspace did not keep running after the network went silent. They stopped
  together.** Bounding when:
  - **Heartbeat.** The 306 heartbeats have a mean interval of 1.187 s, and none is missing. The
    next was due at about [496.2], ≈ 03:48:19.98 host, and it was never printed.
  - **Hung-task reporter.**
    - It had reported pid 1967 at [485.134], [487.210], [489.290], [491.371] and [493.450]: every
      2.08 s, with intervals of 2.076–2.081 s.
    - The next report was due at about **[495.53]**, ≈ 03:48:19.31 host, and it was never printed.
    - An 18 s mmc_rescan block ending in exactly that window is rare. Of 59 healthy batch-3
      episodes that reached the 18 s report, 58 went on to ≥ 20 s (`episodes.py`, 112 episodes
      over runs 1–34).
    - If the I/O path had wedged, the host claim would never have been released and the report
      would have been certain.
  - So the stop came at **board [495.03, ~495.53] ≈ host 03:48:18.82–19.31**, within about 0.5 s
    of the last delivered line. The 1.2 s heartbeat bound ([496.2]) does not depend on the
    hung-task argument.
- **Why this rules out network-only death.** A wifi or SDIO death with the board alive would have
  kept writing heartbeats into the RAM console for the ~9–12 s until the watchdog reset. None is
  there.
- **Why it disfavours "kernel alive, I/O wedged".** That case predicts:
  - the pid 1967 report at roughly 495.5, 497.6, 499.7, 501.8 and 503.9;
  - heartbeats as well. The loop body touches only `/proc`, `/sys` and `/dev/kmsg`, and the
    busybox text it execs was hot in the page cache from running every second.

  Neither appeared.
- **Caveat.** This assumes printk reaches the legacy ramoops console synchronously. That fits a
  non-RT 6.12 kernel, and the line-for-line match with the network stream supports it, but I did
  not re-check it in source.

**Hung-task warnings.**
- There are 12 in this boot, all `Workqueue: events_freezable mmc_rescan`, all with the same trace
  (`__mmc_claim_host` ← `mmc_sd_detect` ← `mmc_rescan`), in three episodes:
  - `kworker/0:3:63`: 10 s at [412.33];
  - `kworker/0:2:34`: 10–14 s at [426.89]–[445.61], then 10–12 s at [464.33]–[466.41];
  - `kworker/0:1:1967`: 10–18 s at [485.13]–[493.45]. This one was still blocked at the freeze.
- The last report in full:

      [  493.449802] INFO: task kworker/0:1:1967 blocked for more than 18 seconds.
      [  493.449957] task:kworker/0:1     state:D stack:0     pid:1967  tgid:1967  ppid:2      flags:0x00200000
      [  493.450018] Workqueue: events_freezable mmc_rescan
      [  493.450098]  __schedule from schedule+0x28/0x138
      [  493.450189]  schedule from __mmc_claim_host+0xdc/0x1d4
      [  493.450256]  __mmc_claim_host from mmc_sd_detect+0x1c/0x74
      [  493.450315]  mmc_sd_detect from mmc_rescan+0xa8/0x354
      [  493.450362]  mmc_rescan from process_one_work+0x134/0x340
      [  493.450419]  process_one_work from worker_thread+0x168/0x2f0
      [  493.450495]  worker_thread from kthread+0xc4/0xe4
      [  493.450547]  kthread from ret_from_fork+0x14/0x28

- **No task other than `mmc_rescan` was reported, at any point in the boot.** rauc, the heartbeat
  shell, sshd, journald and systemd never blocked for 10 s.
- The pattern matches the healthy runs: all 34 show only `events_freezable mmc_rescan`, the first
  report at +76–135 s, and the longest block 16–79 s. This run had its first report at +75 s and
  reached 18 s.

**Other messages.** A case-insensitive search of the whole record for
oom/rcu/lockup/stall/panic/oops/BUG/warn/voltage/throttl/brcmf/sdhost/mmc[0-9]/error/timeout/fail/reset
finds only:
- probe banners (`sdhost-bcm2835 … loaded - DMA enabled`, `mmc0: new high speed SDHC card`,
  `mmc1: new high speed SDIO card`);
- the brcmfmac firmware load at [21.5]–[22.2];
- the systemd watchdog setup (`Watchdog running with a hardware timeout of 14s.`);
- two `kauditd_printk_skb: 4 callbacks suppressed`.

There was **no** mmc, sdhost or brcmfmac error, no RCU or OOM line, and no `Undervoltage
detected!`. There is no `dmesg-ramoops-*` file, so no oops or panic was dumped.

**Under-voltage, measured more precisely than in reset 2.**
- `uv` is `in0_lcrit_alarm` of `rpi_volt`. In this kernel's source
  (`drivers/hwmon/raspberrypi-hwmon.c`, 6.12.93 work-shared tree) it is the firmware's **sticky**
  under-voltage bit, BIT(16). The driver reads it and clears it every 2 s, and prints `dev_crit
  "Undervoltage detected!"` when it sets.
- So `uv=0` in all 127 `[stats]` samples and all 306 heartbeats means the firmware detected no
  under-voltage at any time up to the last poll before [495.03], which came no more than 2 s
  earlier.
- A sag in the final ~2 s, or at the freeze itself, is **not** covered: the next poll never ran.

## 3. The current boot (read 03:57:21 and 03:57:55 host)

- **The kernel started at 03:48:36.162** (board, NTP-synced). Cross-checks:
  - `dmesg --time-format iso` gives `2026-10-31T03:48:36,162000-04:00 Booting Linux on physical CPU 0x0`.
  - Uptime was 559.30 s at board epoch 1793433475 (integer seconds).
  - boot_id `fee5530d…`, which is journal boot 0. Boot −1 is `475c4db8…`, last entry 03:48:05;
    the on-disk journal lagged the freeze by 13 s.
  - **Verified: this boot is the one that followed the 03:48:18 freeze.** The kernel started
    17.34 s after the last delivered line.
- **The firmware's reset-cause copy:**

      rsts:      00000020
      partition: 00000000
      tryboot:   00000000
      boot-mode: 00000001

  Decoded per `reset2-rsts-pstore.md` §1:
  - only **HADWRF** (bit 5, the watchdog full reset) is set;
  - **HADPOR** (bit 12) is clear, as are HADSR*, HADWRH/Q and HADDR*;
  - the partition bits are 0.

  This is a warm, watchdog-driven reset, not a power-on. The same caveat applies as before: a
  `reboot` or a panic restart sets the same bit. pstore (§2) rules out a panic, and no reboot was
  requested mid-copy. There is still no cold-boot control reading.
- **Reset delay R.**
  - From the stop window (03:48:18.82–19.31) to kernel start is **16.85–17.35 s**.
  - The warm reset-to-kernel time F is ≤ 7.43 s. That figure is from `reset2-analysis.md` §4
    (14 batch-2 reboots). I did not re-measure it in batch 3. One batch-3 reboot, boot −2's last
    entry at 03:39:56 to boot −1's start at 03:40:03.78, gives 6.8–7.8 s at 1 s resolution, which
    agrees.
  - So **R ≥ 9.4 s**: about 9.4–10.0 s if the shutdown tail is near zero, and up to ~12 s with a
    2–3 s tail. That is inside the 7–14 s watchdog window (`timeout=14`, systemd pets every 7 s,
    `bootstatus=0` as before). Reset 2 gave R ≥ 10.7 s.
- **uv flag now:** `/sys/class/hwmon/hwmon1 in0_lcrit_alarm=0`. The current dmesg has no voltage
  or throttle line.
- **rauc status:**
  - Booted from `rootfs.1 (B)` and Activated `rootfs.1 (B)`.
  - `[rootfs.1]` (/dev/mmcblk0p3) booted, boot status **good**.
  - `[rootfs.0]` (/dev/mmcblk0p2) inactive, boot status **bad**. That is the interrupted install
    target.
  - `fw_printenv` reads `BOOT_ORDER=B`, `BOOT_A_LEFT=0`, `BOOT_B_LEFT=3`.
  - The board runs on the slot it was on before the install. The half-written A is marked bad and
    taken out of the boot order.
- **Other state read:**
  - 0 pstore mounts.
  - No hb245 process.
  - `hung_task_timeout_secs=120`, `check_interval=0` and `warnings=10`. These are the defaults, so
    the diagnostics died with boot −1 as designed.
  - `FAT-fs (mmcblk0p1): Volume was not properly unmounted` at [14.72]. This is /boot's dirty bit
    after an unclean reset, the same observation as in reset 2. /boot has no A/B protection.

**A correction to the brief's premise about `printk_devkmsg`.**
- The loop LOG does show `sysctl: write error: Invalid argument` /
  `sysctl missing or failed: kernel.printk_devkmsg=on`.
- But the **current** boot, which nothing armed (the hung-task values are back at their
  defaults), reads `printk_devkmsg=on`. The kernel cmdline has no `printk.devkmsg` token.
- So the image appears to boot with devkmsg already `on`, and the write's EINVAL most likely means
  the setting is locked. Who sets it is not established.
- It does not matter to this analysis. The record holds no devkmsg ratelimit line, and all 306
  heartbeats are present at a steady 1.19 s interval. **Heartbeat integrity is measured directly**,
  not assumed.

## 4. What froze, compared with reset 2

| | reset 2 (batch 2, run 14) | **reset 3 (batch 3, run 35)** |
|---|---|---|
| Last sign, relative to capture start | 138.9 s (`[stats]`) | **157.6 s / 157.96 s** (`[stats]` / `[kernel]` heartbeat) |
| rauc progress at freeze | 84% | **90%** |
| Streams | `[stats]` ran to the end; sessions dropped 6.8 / 7.8 s later | Same, 6.65 / 7.65 s |
| Network-independent record | Console ended 136 s earlier (nothing printed; no heartbeat existed) | **Heartbeat ends on the same line the host got last; khungtaskd's due report absent** |
| Blocked tasks | Not observable (120 s threshold) | Only the routine mmc_rescan claim_host, 18 s |
| Panic/oops | None (console, no dmesg zone) | None |
| RSTS | 0x20 HADWRF | **0x20 HADWRF** |
| R (freeze to reset) | ≥ 10.7 s | **≥ 9.4 s** |
| uv | 0 at 1 Hz (current bit, not known then to be sticky) | 0; sticky bit polled every 2 s, clear up to ≤ 2 s before the stop |

Reset 1 (`run1-reset.log`) died at 80%. Its sessions ended 138.4 s in, so the last sign was about 131 s in (inferred). **Across n = 3 the freeze is not at a
fixed image offset (80/84/90%) or a fixed elapsed time (~131/139/158 s).** All three fall in the
last third of the slot copy, under sustained ~15 MB/s SD writes, with three ssh streams on SDIO
wifi. That weakens the "same card region" idea that reset 2 left open.

**What the last evidence of activity says.**
- No subsystem was blocked, apart from the routine host-claim wait.
- The I/O path was completing writes at full rate in the last sample.
- Then everything stopped together: userspace, the timer-driven khungtaskd, and the network.
- That is the signature of the CPU or the system bus stopping, rather than any one driver hanging
  while the kernel stays up. Two candidates remain, and the board cannot tell them apart:
  1. **A SoC, bus or CPU lockup.** For example, an AXI or peripheral access that never completes
     (SD host or SDIO) and stalls the single ARMv6 core, or a stall with interrupts off. This
     kernel has no softlockup detector and TINY_RCU. ARMv6/BCM2835 has no NMI watchdog, so it
     could not print a line.
  2. **A supply sag that hangs the SoC without a power-on reset.** RSTS sees only the watchdog
     that followed. The sticky UV bit covers up to ~2 s before the stop, not the stop itself.

**What remains open.**
- Which of those two it is.
- Whether the SD write path, the SDIO wifi path, or their concurrency is the trigger. Batch 3 reset first at run 35;
  batch 2 reset first at run 14.
- The RSTS cold-boot control (expect 0x1000 after a smart-plug cycle) is still unread.

**The single next diagnostic that would decide it.**
- **A fast external log of the board's 5 V input across the next reset.** That means a
  millisecond-resolution logger or scope on the supply, not a 1 Hz smart plug.
  - If the rail stays in spec through the 0.5 s stop window, power is out, and the cause is a SoC
    or bus lockup.
  - If it dips there, the cause is power.
- It needs no image, /boot or board change, so it is entirely host-side. The in-band instruments
  have reached what this kernel can say: the heartbeat now pins the stop to ~0.5 s, and nothing
  inside the board can see past it.
- This is my lean. Whether the bench has such a logger is the owner's to say.

## Classes and revert

- **Nothing was changed on the board,** so there is nothing to revert.
- The two read sessions ran only:
  - `date`, `cat` of /proc, /sys and device-tree files;
  - `hexdump` of the `chosen/bootloader` properties;
  - `dmesg`, `journalctl`, `ps`, `rauc status`, `fw_printenv`.
- pstore was not mounted, so the kernel still holds boot −1's record for a re-read
  (`mount -t pstore -o ro pstore /sys/fs/pstore`, copy, `umount`; never `rm`). The loop's byte copy
  in the record dir is the one analysed.
- Host-side, I wrote files only under `scratchpad/reset3/` and this file.

## Measurement notes

- **Board reads:** 2 sessions, each once. RSTS was read once this boot (n = 1 per reset; n = 2
  across resets, both 0x20). There is still no cold-boot control.
- **Healthy comparison:** batch-3 runs 1–34, same sha, same board, same loop and diagnostics. I
  compared them; the samples were not pooled with run 35.
- **Not re-checked in source:** that printk writes the legacy ramoops console synchronously on
  this kernel.
- **From reset 2, not re-measured:** F ≤ 7.43 s.
- **Re-checked in source:** the sticky-bit reading of `uv`.
