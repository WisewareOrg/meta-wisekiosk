# Reset 5 analysis: batch-7 run 65 (#245 mid-install hard reset, BFQ, first reset with the wdt/PID1 heartbeat)

Bench board only, read-only. I changed nothing on the board: no reboot, no install, no mount, no
/boot write, no pstore access (`loop7.sh` had already copied and unmounted it), no sysctl, no
sysfs or debugfs write. Prod was not contacted. `~/meta-wisekiosk`'s git state was not touched
(branch `245-ota-log-capture`, clean). There was one board session:
`flock -o -w 900 ~/wisekiosk-bench/records/lock ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@<BENCH_ADDRESS> sh -s < reset5-remote-read.sh`,
with every output line stamped on the host as it arrived. Address, hostname, MAC and machine-id
appear here as `<BENCH_ADDRESS>`, `<BENCH_HOSTNAME>`, `<BOARD_MAC>` and `<KIOSK_MACHINE_ID>`.

- **Record.** `records/20261101T090332Z`, test commit `8207d14bb452`, `exit_status` 90. Loop
  summary (`scratchpad/bench/loop7/summary.txt` in the checkout):
  `2026-11-01T04:11:33-0500 run=65 sha=8207d14b… exit=2 record=records/20261101T090332Z reset=yes`.
  Runs 1–64 of batch 7 were clean. That makes 84 clean BFQ installs (batch 6: 20, batch 7: 64)
  before this one.
- **Arming verified** from `loop7/LOG` for run 65: `scheduler=none mq-deadline kyber [bfq]`,
  `kernel.hung_task_timeout_secs = 10`, `kernel.hung_task_check_interval_secs = 2`,
  `kernel.hung_task_warnings = -1` (`printk_devkmsg=on` failed, as in every run). There are 65
  BFQ readbacks and 65 hung-task armings, one per run.
- **pstore copy.** `records/20261101T090332Z/pstore/console-ramoops-0`, 560 lines, md5
  `45acb1a95645614d292bba75218b7f64`. It is the only file. Its kernel command line carries
  `<BOARD_MAC>`.
- **Scripts and raw outputs** are in `scratchpad/reset5/`. The `.out` files are unredacted except
  `stdout.redacted`.
  - `final30.py`: the final N heartbeats, pstore joined with the host stream.
  - `clocks.py`: offsets and kernel start.
  - `timing.py`: the watchdog timing test.
  - `pets.py` and `wdtrate*.py`: pet-interval bounds and watchdog clock-scale feasibility.
  - `progress.py` and `phase.py`: copy position, and the healthy comparison at the same position.
  - `reset5-remote-read.sh` was run once, giving `reset5-remote-read.out`.
  - Committed `metrics.py` was run over all 65 batch-7 records, giving `b7metrics.txt`.
- **Clocks.** Times are **host** (`-0500`; DST ended overnight) unless marked *board* or
  *printk*.
  - Host = board + 0.042 s. This is the minimum of host-receive minus board-stamp over the 221
    `[kernel]` heartbeat lines, so it includes the latency floor.
  - printk ↔ board: `[435.199029]` is board `04:06:30.118226`, on the same line.

## Verdict

1. **The watchdog did not count down from the last heartbeat, and PID1 was never stalled.**
   - In all 221 heartbeats, PID1 was `S do_epoll_wait` (one `R`). `p1majflt` was a constant 143.
   - `wdt` cycled 13→7 with no value below 7.
   - The last line, `[435.199]`, is ordinary: `wdt=7 p1=S p1wchan=do_epoll_wait`.
2. **The timing test rejects the brief's prediction by ~7 s. It agrees with "one more pet, then 14 s
   of silence".**
   - Predicted reset (last pet + 14 s, no further pet): **04:06:37.38–37.60**.
   - Observed reset (kernel start − B, with B ≤ F): **≥ 04:06:44.77**, or about 44.77–44.88 if
     the shutdown tail is near zero.
   - The miss is +7.2 s (+6.0 s at the slowest watchdog clock the data allows). That is about one
     pet interval, and far outside the ~0.5 s error budget.
   - If PID1 petted once more, at Q ≥ printk 435.80 (7.16 s or more after the previous pet; 7.0–7.21
     s is seen in healthy runs), then went silent, the reset lands at 04:06:43.7–45.1. **That
     agrees with the observed time.**
3. **This is reset 3's shape: the whole board went silent, and the watchdog fired 14 s later.**
   - The last pet was ~0.6 s after the last heartbeat. After it, nothing ran: no heartbeat, no
     further pet, no printk.
   - That means no hung-task report and no sdhost 10 s timeout, either of which a live kernel
     would have printed before the 14 s ran out.
   - RSTS is again 0x20.
4. **"PID1 starved of SD reads → hardware watchdog" is not the mechanism of this reset (strong).**
   The watchdog is very probably the reset agent (moderate–strong), but it was acting as the
   recovery for a board that had stopped.
   - BFQ removed the PID1-starvation near-miss: 0 of 85 BFQ runs dipped below 7, against 2 of 25 in
     batch 5 on the default elevator.
   - It did not remove the reset. 1/85 against 3/114 is not distinguishable (Fisher p = 0.64).

## 1. The final 30 heartbeats (pstore and host `[kernel]` stream)

**pstore and host agree exactly.** Both hold 221 heartbeats, and the set difference is empty in
both directions. The final line of each is `[435.199029] hb245 434.77 … wdt=7 p1=S
p1wchan=do_epoll_wait p1majflt=143`. pstore holds **nothing after it**: no heartbeat, oops, panic,
`reboot:`, mmc, sdhost, brcmfmac, RCU, soft-lockup or hung-task line. There is no
`dmesg-ramoops-*` file.

In the table, dR is reads completed, dWs is write sectors, and both are deltas since the
previous heartbeat (mmcblk0 stat). `p1majflt` is 143 in every row and is omitted.

| host recv | board | printk | wdt | p1 | p1wchan | load1 | Dirty kB | WB kB | dR | dWs |
|---|---|---|---|---|---|---|---|---|---|---|
| 04:05:50.499 | 04:05:50.451 | 395.532 | 11 | S | do_epoll_wait | 2.75 | 15304 | 1028 | 20 | 26664 |
| 04:05:51.761 | 04:05:51.715 | 396.796 | 10 | S | do_epoll_wait | 2.85 | 6144 | 512 | 10 | 22688 |
| 04:05:53.182 | 04:05:53.119 | 398.200 | 9 | S | do_epoll_wait | 2.85 | 15816 | 0 | 37 | 0 |
| 04:05:54.781 | 04:05:54.726 | 399.807 | 8 | S | do_epoll_wait | 2.85 | 24000 | 0 | 27 | 0 |
| 04:05:56.364 | 04:05:56.098 | 401.179 | 13 | S | do_epoll_wait | 2.85 | 26972 | 516 | 22 | 13344 |
| 04:05:57.538 | 04:05:57.492 | 402.573 | 11 | S | do_epoll_wait | 2.94 | 19004 | 1028 | 17 | 26800 |
| 04:05:58.944 | 04:05:58.894 | 403.975 | 10 | S | do_epoll_wait | 2.94 | 10920 | 0 | 19 | 25744 |
| 04:06:00.453 | 04:06:00.402 | 405.483 | 9 | S | do_epoll_wait | 2.94 | 21568 | 0 | 42 | 0 |
| 04:06:01.847 | 04:06:01.788 | 406.869 | 7 | S | do_epoll_wait | 2.87 | 29652 | 0 | 36 | 1056 |
| 04:06:03.167 | 04:06:03.107 | 408.188 | 13 | S | do_epoll_wait | 2.87 | 28508 | 516 | 28 | 13312 |
| 04:06:04.458 | 04:06:04.412 | 409.493 | 12 | S | do_epoll_wait | 2.87 | 16928 | 1028 | 11 | 34992 |
| 04:06:05.754 | 04:06:05.690 | 410.771 | 10 | S | do_epoll_wait | 2.87 | 14408 | 1028 | 35 | 13312 |
| 04:06:07.309 | 04:06:07.265 | 412.346 | 9 | S | do_epoll_wait | 3.04 | 11912 | 0 | 36 | 19656 |
| 04:06:08.712 | 04:06:08.658 | 413.739 | 8 | S | do_epoll_wait | 3.04 | 22540 | 0 | 71 | 0 |
| 04:06:10.067 | 04:06:10.023 | 415.103 | 13 | S | do_epoll_wait | 3.04 | 27336 | 516 | 31 | 11264 |
| 04:06:11.399 | 04:06:11.340 | 416.421 | 12 | S | do_epoll_wait | 3.12 | 16444 | 516 | 8 | 31888 |
| 04:06:12.791 | 04:06:12.742 | 417.822 | 10 | S | do_epoll_wait | 3.12 | 21712 | 0 | 37 | 6176 |
| 04:06:14.299 | 04:06:14.255 | 419.335 | 9 | S | do_epoll_wait | 3.12 | 27396 | 1028 | 20 | 9376 |
| 04:06:15.638 | 04:06:15.596 | 420.677 | 8 | S | do_epoll_wait | 3.12 | 22332 | 516 | 28 | 18432 |
| 04:06:17.026 | 04:06:16.974 | 422.055 | 13 | S | do_epoll_wait | 3.11 | 15292 | 1028 | 12 | 33944 |
| 04:06:18.419 | 04:06:18.368 | 423.449 | 12 | S | do_epoll_wait | 3.11 | 12188 | 0 | 12 | 20520 |
| 04:06:19.728 | 04:06:19.680 | 424.761 | 10 | S | do_epoll_wait | 3.11 | 32008 | 1024 | 8 | 16384 |
| 04:06:20.948 | 04:06:20.896 | 425.977 | 9 | S | do_epoll_wait | 3.11 | 46880 | 1028 | 0 | 27800 |
| 04:06:22.188 | 04:06:22.139 | 427.220 | 8 | S | do_epoll_wait | 3.18 | 45508 | 592 | 0 | 42088 |
| 04:06:23.620 | 04:06:23.560 | 428.641 | 13 | S | do_epoll_wait | 3.18 | 19068 | 26672 | 0 | 29904 |
| 04:06:24.849 | 04:06:24.801 | 429.882 | 12 | S | do_epoll_wait | 3.18 | 21888 | 23556 | 0 | 34832 |
| 04:06:26.051 | 04:06:26.001 | 431.082 | 11 | S | do_epoll_wait | 3.24 | 20756 | 25680 | 1 | 37888 |
| 04:06:27.345 | 04:06:27.299 | 432.379 | 10 | S | do_epoll_wait | 3.24 | 16568 | 29240 | 0 | 37032 |
| 04:06:28.718 | 04:06:28.669 | 433.750 | 9 | S | do_epoll_wait | 3.24 | 17644 | 27716 | 0 | 38912 |
| **04:06:30.382** | **04:06:30.118** | **435.199** | **7** | **S** | **do_epoll_wait** | 3.24 | 31308 | 15184 | 0 | 36000 |

- **Did wdt count down below 7 while PID1 was in D? No.**
  - Over all 221 heartbeats, the wdt counts are 7:18, 8:29, 9:32, 10:35, 11:38, 12:32, 13:37.
  - PID1 was `S do_epoll_wait` 220 times and `R` (wchan 0) once. It was **never `D`**.
  - `metrics.py` gives `min_wdt=7 non_s_p1=[('R','0')] p1_d_seconds=0.0`.
  - In the last 30 rows, pets fall at the 13s: [408.2], [415.1], [422.1], [428.6]. The pet
    intervals are 6.4–7.7 s, inside the healthy envelope.
- **Last wdt value: 7 at printk [435.199]** (board 04:06:30.118, host receipt 04:06:30.382).
  - `timeleft` truncates (`bcm2835_wdt.c`: `WDOG_TICKS_TO_SECS(x) ((x) >> 16)`), so 7 means 7–8 s
    remained.
  - A reading of 7 is what every run shows just before a pet. It is the healthy floor, not a dip.
  - All 65 batch-7 runs have `min_wdt=7`.
- **Load** was 3.24 at the end. The healthy batch-7 maximum over the same copy phase is 3.03–6.15
  (median 3.92, n = 64), so the load was on the low side.
- **mmc progress.**
  - **1 078 274 sectors written** since the first `[stats]` sample, at +73.9 s after `capture
    started`.
  - Healthy runs reach the same volume at 70.6–100.5 s (median 74.3 s, n = 64), so the run was
    **on schedule**. That volume is **~26% of the image's bytes**; a full copy is ~4.21 M
    sectors.
  - The last rauc line was ` 61% Copying image to rootfs.1`; rauc's percentage does not track
    bytes.
  - Resets 1–4 died at 80/84/90/99%, so **this is the earliest reset yet in the copy**.
- **The last ~10 s.**
  - Reads stopped (one 8-sector read after [424.8]), and writes ran at ~14 MB/s with Writeback at
    15–29 MB.
  - Healthy runs over the same write range show the same regime: a longest zero-read stretch of
    2–6 samples (run 65: 5) and max Writeback ≤ 32.8 MB (run 65: 31.2 MB).
  - **No precursor.**
- **Hung-task reports: none** in this boot, against an armed 10 s/2 s detector.
  - **0 reports across all 65 batch-7 install windows.** BFQ removed the routine `mmc_rescan`
    reports of batches 3–4, so here the silence has no base rate behind it.
  - It still counts as a conditional witness; see §3.
- **uv** was 0 in every heartbeat and `[stats]` sample. `freq=900000` throughout (governor
  `ondemand`, capped).

**Host side.**

    2026-11-01T04:05:16.203960-0500 capture started
    04:06:29.114986 [journal] … hb245 433.42 … wdt=9 p1=S …       (last journal line; lag 0.43 s)
    04:06:30.068391 [stats]   … Writeback:18288 … mmc=5455 565 635358 72944 2390 140557 1343068 …   (last stats)
    04:06:30.382172 [kernel]  2026-11-01T04:06:30,118226-05:00 hb245 434.77 … wdt=7 p1=S p1wchan=do_epoll_wait p1majflt=143
    04:06:37.092842 [journal] Timeout, server <BENCH_ADDRESS> not responding.
    04:06:37.094578 [stats]   Timeout, server <BENCH_ADDRESS> not responding.
    04:06:38.094934 [kernel]  Timeout, server <BENCH_ADDRESS> not responding.
    Read from remote host <BENCH_ADDRESS>: Connection reset by peer   (unstamped: the rauc-install ssh)
    2026-11-01T04:11:30.370854-0500 capture stopped

- The sessions dropped 7.0, 7.0 and 7.7 s after the last data. That is the `ServerAlive` 2 × 3
  signature, with the usual 1 s split, as in resets 2–4.
- The `[stats]` sample due at ~04:06:31.2 (cadence 1.11–1.32 s over the last 10) never arrived.
- **Latency of the final `[kernel]` line.** It was 0.264 s, against a typical 0.05 s (in-window
  median 0.051 over the last 60).
  - In healthy batch-7 windows the p99 is 0.250 s, and 30 of 7 796 lines are ≥ 0.264 s.
  - That is rare but not unique. **Weak** evidence that the board was sluggish in its last 0.3 s,
    and not a precursor I would lean on.
- The `[journal]` copy of [434.77] never arrived. Healthy journal lag reaches 4.9 s (p99 1.15 s),
  so **its absence proves nothing**.

## 2. Timing test of the watchdog hypothesis

**Inputs.**
- **The last pet before the final heartbeat, P.**
  - Each heartbeat reads `timeleft` between its uptime field u and its printk time pk.
  - A reading w therefore bounds the pet: `t − 14 + w ≤ P < t − 13 + w`.
  - Intersecting the five samples since the [428.641] wdt=13 sample (pstore's exact printk times)
    gives **P ∈ [428.42, 428.64]** printk.
- **Kernel start of the current boot, K = 04:06:52.195 host.** This is the minimum of
  host-receive minus `/proc/uptime` over 20 host-stamped samples (spread 0.23 s; resolution 0.01
  s).
  - Cross-check: the board's `dmesg --time-format iso` head is `2026-11-01T04:06:52,155621-05:00`,
    and adding the 0.042 offset gives 04:06:52.198. **They agree to 3 ms.**
- **Last heartbeat to kernel start: 22.04 s.** Reset 4 was 7.65 s, reset 3 17.34 s.
- **B, the reset-to-kernel time** (firmware, u-boot and kernel to printk zero).
  - F (from "Journal stopped" to kernel start, on a warm reboot) = B + the shutdown tail, so
    **B ≤ F**.
  - F is 7.32–7.43 s over n = 16: 14 from batch 2, 1 from reset 4, and **1 fresh today**. Boot −2
    logged `03:59:07.490427 systemd-journald[92]: Journal stopped`, and boot −1's printk zero is
    board 03:59:14.919 (= 04:06:30.118226 − 435.199029 s), so **F = 7.429 s**.
  - The tail itself is still unmeasured.
- **Observed reset = K − B ≥ 04:06:44.77 host** (printk ≥ 449.80). It is 04:06:44.77–44.88 if
  the tail is ~0, and later by the tail otherwise.

**The brief's prediction, "last heartbeat time + last wdt value":**

| | printk | host |
|---|---|---|
| last heartbeat | 435.199 | 04:06:30.16 |
| + wdt (7, truncated, so 7–8 s left) | 442.2–443.2 | 04:06:37.2–38.2 |
| tighter, via P + 14 s | 442.42–442.64 | **04:06:37.38–37.60** |
| observed reset (K − B) | ≥ 449.80 | **≥ 04:06:44.77** |

**They disagree by +7.2 s.** That is far outside the error budget:
- F's spread, 0.11 s;
- the clock offset, < 0.05 s;
- K, ±0.01 s;
- the watchdog clock-scale uncertainty below, < 1.2 s.

To close the gap, B would have to be ~14.6 s, twice every measured F. Reset 4's 7.648 s gap
already rules that out for a reset with RSTS 0x20.

**The variant that does agree: one more pet, then nothing.**
- The last sample (wdt=7, elapsed 6–7 s) was taken right before a pet was due.
- If PID1 petted once more at Q and then never again, the reset lands at **Q + 14 s**.
- Matching the observed ≥ 449.80 needs **Q ≥ 435.80**, which is Q − P ≥ 7.16 s.
- Is a 7.16 s pet interval healthy? I bounded every pet interval in batch 7 the same way:
  - 3 989 intervals in all;
  - **172 are provably longer than 7.0 s, and the longest provable is ≥ 7.21 s**;
  - none is provably longer than 7.5 s.
- So a pet at 435.8–435.9, on time within healthy scheduling slack, followed by 14 s of silence,
  reproduces the observed reset **to within 0–0.1 s** for a near-zero tail.
- If the tail is not near zero, the residual grows by the tail, and the pet must have been
  correspondingly later (≤ 7.5 s is still plausible).

**Watchdog clock scale.**
- If the PM watchdog's tick were not exactly 1/65 536 s of uptime, the 14 s would stretch.
- I scanned a scale k (hardware s → uptime s) over all 221 × 65 batch-7 heartbeats.
  - k = 1.00 is feasible once the read window allows the measured minimum printk lag (0.106 s,
    from pstore) plus ~0.05 s.
  - Without that allowance the fit prefers k ≈ 1.03–1.08.
- So k ∈ [1.00, 1.08] is carried as uncertainty, **not measured**.
- Across that range, "no further pet" still misses by +6.0 to +7.2 s. "One more pet" agrees, and
  needs Q ≥ 434.7–435.8.

**Conclusion.** The reset is consistent with the hardware watchdog expiring **14 s after a final pet
that came ~0.6 s after the last heartbeat** (k = 1; earlier for k > 1). It is **not** consistent with
the watchdog having counted down from the last heartbeat while PID1 stalled.

## 3. PID1 was not stalled: what stopped

**The bracket (k = 1).**
- PID1 was alive and pinging at Q ≈ printk 435.8–435.9, host ≈ 04:06:30.76–30.86.
- The next heartbeat (due ≈ [436.3–436.6]) and the next `[stats]` sample (due host ≈ 04:06:31.2)
  never came.
- So **everything stopped within about 0.4–0.7 s after PID1's last pet**, at about host
  04:06:30.8–31.2. For k up to 1.08 the bracket widens to [434.7, 436.5].

**Whole board, or userspace only?**
- **For a kernel that stopped:**
  - Nothing printed for the ~14 s up to the reset.
  - **khungtaskd.**
    - It was armed at 10 s with a 2 s check (verified in LOG).
    - It would have reported any `TASK_UNINTERRUPTIBLE` task blocked since ~436, between ~[446] and
      [448.5], before the reset at ≥ [449.8].
    - That covers PID1 in `__ext4_find_entry` (the batch-5 near-miss wchan). That path ends in
      `wait_on_buffer` → `wait_on_bit_io(…, TASK_UNINTERRUPTIBLE)`, checked in
      `fs/buffer.c` of the 6.12.93 work-shared tree.
    - It also covers writeback kworkers waiting on a card that stopped completing requests.
  - **sdhost.** It arms a **10 s** software timer per command (`bcm2835-sdhost.c`:
    `timeout += 10 * HZ; mod_timer(&host->timer, timeout)`), and on expiry prints `timeout waiting
    for hardware interrupt`. A stuck SD command on a live kernel would have printed that before
    the watchdog.
  - **Console path.** pstore and the host stream hold the identical 221 lines up to the very last,
    so printk was reaching ramoops promptly up to the stop. A later `pr_err` should have landed.
    The synchronous-console property was not checked in source.
- **Against (what a live kernel could hide):**
  - Page-fault and dirty-throttle waits are `TASK_KILLABLE`, and khungtaskd skips them (reset 4
    §2). A userspace-wide stall on page-ins would print nothing.
  - **But it would need the SD to stop serving reads for 14 s** while the kernel stayed alive.
    With 31 MB Dirty and 15 MB Writeback at ~14 MB/s, writeback drains in ~3–4 s, and then page-ins
    are served.
  - A card that stopped completing requests brings back the sdhost 10 s print and the D-state
    kworker report. So this reading needs a stall that is both silent and long.
- **Lean (inference, not measured):** the kernel itself stopped, a CPU or bus lockup like reset 3,
  about 0.5 s after PID1's last pet. The hardware watchdog then reset the board 14 s later, which
  is the recovery working as designed.

**Sessions.** The three ssh sessions went silent within 0.3 s of one another and dropped on the
ServerAlive timeout; there was no RST from a live kernel. That is the same as resets 2–4.

**Other context.**
- `kiosk-soak.service` last ran in boot −1 at 04:04:15–04:04:18, a minute before the install
  started at 04:05:16. The timer is 5-minutely, so the next run was due ~04:09:15, after the
  reset. **Soak was not running during the install window or at the stop.**
- Nothing else is in the boot −1 journal between 04:05:40 and the end except heartbeats; the
  non-heartbeat grep was empty.

## 4. The current boot (read 04:19:02–04:19:12 host)

- **Kernel start:** 04:06:52.195 host, and board `2026-11-01T04:06:52,155621-05:00` (§2). boot_id
  `ccfd7c10…`.
- **`journalctl --list-boots`.**
  - −1 `ab1ed6ca…` 03:59:08 → **04:06:28** (the on-disk journal ends at hb [433.42]);
  - 0 starts "04:05:51", which is the clock restored from the timesync stamp before NTP sync. It
    is not the kernel start.
- **Reset-cause copy:** `rsts: 00000020`, `partition: 00000000`, `tryboot: 00000000`,
  `boot-mode: 00000001`.
  - Decoded per `reset2-rsts-pstore.md` §1, **HADWRF (bit 5, watchdog full reset) is the only bit
    set**, and HADPOR is clear.
  - It is the same value as resets 2, 3 and 4, so **n = 4 of 4**.
  - It is consistent with the watchdog. It does not exclude other writers of PM_RSTC, but the
    kernel's restart path would have printed and did not.
- **uv:** `/sys/class/hwmon/hwmon1 in0_lcrit_alarm=0`. No voltage or throttle line in dmesg.
  Thermal 31.5 °C at idle.
- **rauc status.**
  - Booted `rootfs.0 (A)`, Activated `rootfs.0 (A)`.
  - `[rootfs.0]` (/dev/mmcblk0p2) booted and **good**. `[rootfs.1]` (/dev/mmcblk0p3) inactive and
    **bad**: the interrupted install target.
  - `fw_printenv`: `BOOT_ORDER=A`, `BOOT_A_LEFT=3`, `BOOT_B_LEFT=0`. **The fallback worked as
    designed.**
- **Scheduler:** `none [mq-deadline] kyber bfq`. **The default mq-deadline is back**, so the
  loop's bfq switch was runtime-only, as designed.
- **Other state.**
  - pstore mounts 0, hb245 processes 0.
  - `hung_task_timeout_secs=120`, `check_interval=0`, `warnings=10` (defaults restored).
    `printk_devkmsg=on`.
  - vm dirty defaults: `dirty_ratio=20`, `dirty_background_ratio=10`, `dirty_bytes=0`,
    `dirty_expire_centisecs=3000`, `dirty_writeback_centisecs=500`.
  - watchdog0: `timeout=14`, `timeleft=8`, `bootstatus=0`, `status=0x8000`.
    `RuntimeWatchdogUSec=14s`, `RuntimeWatchdogPreUSec=0`.
  - dmesg: `EXT4-fs (mmcblk0p2): INFO: recovery required on readonly filesystem … recovery
    complete`, which is rootfs.0's journal replayed after the unclean stop. Also `FAT-fs
    (mmcblk0p1): Volume was not properly unmounted` at [14.65], /boot's dirty bit again as in
    reset 4. Neither is a write that I made.
  - Governor `ondemand`.

## 5. Verdict detail

**Is "PID1 starved of SD reads → hardware watchdog" confirmed for this reset?** **No. It is
refuted as this reset's mechanism (strong).**
- The instrument built to see it ran to the last line and saw a healthy PID1.
  - PID1 was never in D, and its major-fault count never moved.
  - wdt never went below the healthy 7.
- The timing says PID1 **petted once more** after the last heartbeat.

The **hardware watchdog as the reset agent is supported (moderate–strong):**
- RSTS 0x20;
- 14 s of total silence that ends exactly when a last-pet-plus-14 s expiry predicts, with a
  residual of 0–0.1 s for a near-zero shutdown tail;
- the alternative, a reset at the moment of the stop, would have put the kernel start at ~7.4 s
  after the last heartbeat (as in reset 4), not 22 s.

But the watchdog fired **because the board had stopped**, not because PID1 alone was starved. It is
recovery, not cause.

**What this means for BFQ.**
- **It removed the PID1-starvation near-miss.**
  - Default elevator, batch 5 (same instrument): 2 of 25 runs dipped to wdt=4 with PID1 D in
    `__ext4_find_entry`.
  - BFQ, batches 6 + 7: **0 of 85** runs went below 7. In batch 7, PID1 D totalled at most 3.1 s
    in a run (run 1) and 1.4 s in run 14 (`mmc_blk_rw_wait`). Batch 6's D episodes
    (`__ext4_get_inode_loc`, `folio_wait_bit_common`) also never took wdt below 7.
  - BFQ also removed every `mmc_rescan` hung-task report (0 in 65 windows).
- **It did not remove the reset, and the data cannot say it reduced it.**
  - BFQ 1/85 = 1.2% (exact 95% CI 0.03–6.4%) against default 3/114 = 2.6% (0.55–7.5%).
  - Fisher two-sided **p = 0.64**.
- **The near-miss and the reset are probably different mechanisms.**
  - Fixing PID1's read latency fixed the near-miss and left a reset whose shape (whole-board
    silence → watchdog) matches reset 3.
  - Reset 4 (R ≈ 0.3–2 s, nothing printed) remains the odd one out.
  - Copy position across resets is 80/84/90/99/26%. That looks like a hazard spread over the
    sustained-write window, not a specific phase. This is inference at n = 5.

**What blocked PID1:** nothing that was observed. It was `S do_epoll_wait` at every sample, and the
board stopped within ~0.5 s of its last pet.

**Next lever. My lean, and a decision for the owner.** The levers on the list target PID1's I/O
latency, which BFQ has already fixed:
- **`IOWeight`/ionice for rauc.** Under BFQ this only shifts rauc's share against competing I/O.
  In the final 10 s there were no competing reads at all (dR = 0), so it would not have changed
  this window. Expected effect on this reset: **none**.
- **Stopping `kiosk-soak.timer` during the install.** Soak was not running in this install window
  (§3). Expected effect on this reset: **none**.
- **Dirty limits (`dirty_bytes`/`dirty_background_bytes`).** These reshape the writeback bursts,
  and Writeback was 15–31 MB in flight at the stop, but rauc still streams ~2 GB at card speed.
  - They help only if the freeze scales with burst size, which is untested.
  - Class: runtime sysctl, reverts at reboot.
- **A sustained write-rate cap on rauc** (cgroup v2 `io.max wbps`, which is blk-throttle,
  independent of the elevator). This is the lever that matches a hazard spread over the
  sustained-write window: fewer MB/s for longer.
  - It is a guess at the mechanism.
  - It is recoverable over the wire (a `systemd-run -p IOWriteBandwidthMax=` scope or a runtime
    cgroup write), and an n = 85 batch would be needed to say anything.
- **Longer watchdog.**
  - The premise needs a correction. The 15.99 s cap is per *hardware* ping (`max_hw_heartbeat_ms =
    0xfffff*1000>>16`). The kernel watchdog core can serve a longer userspace timeout by pinging
    the hardware itself. Verified that the driver sets `max_hw_heartbeat_ms` and no `max_timeout`;
    the core behaviour is from the watchdog-core design, not re-read here.
  - **But it is moot and harmful here.** A frozen kernel stops the core's pinger too, so the reset
    happens anyway, only later. A longer timeout would only help the PID1-starvation mode, which
    BFQ already removed.
  - Not recommended.
- **What I would do before any mitigation:** discriminate "kernel stopped" from "silent userspace
  stall". Two runtime-only, read-mostly diagnostic sysctls, both of which revert at reboot:
  - `kernel.watchdog_thresh=4` (soft-lockup report at 8 s), if the soft-lockup detector is built;
  - `/sys/module/rcupdate/parameters/rcu_cpu_stall_timeout=5`.
  - If the next reset prints a soft-lockup or RCU stall, the CPU was taking interrupts but stuck,
    and the backtrace names where. Continued silence means the CPU stopped taking interrupts, a
    hardware or bus lockup, which points the investigation at supply and the SD/SDIO bus rather
    than the I/O stack.
  - **Unverified on this image:** whether these knobs exist (no `/proc/config.gz`). That is a
    read-only check for next time.
  - Arming them is the owner's call; I have not done it.

## Classes and revert

- **Board changes: none, so there is nothing to revert.** The single session ran only `cat` of
  /proc and /sys files, `hexdump` of /proc/device-tree, `dmesg`, `journalctl`, `ps`,
  `rauc status`, `fw_printenv`, `systemctl show`/`list-timers` and `date`.
- pstore was not mounted, and nothing was deleted.
- Host side, I wrote only `scratchpad/reset5/*` and this file. I stopped my own stray `find` (a
  search for the loop summary), which had been reading and writing nothing on the board.

## Measurement notes

- **Board sessions:** 1. RSTS was read once (n = 1 this reset; n = 4 across resets, all 0x20).
- **K:** 20 host-stamped uptime samples, using the minimum-latency estimator, cross-checked
  against dmesg (Δ 3 ms).
- **F:** n = 16, 7.32–7.43 s, all warm reboots; the shutdown tail is unmeasured. B ≤ F is the
  only bound used.
- **Healthy comparison:** batch-7 runs 1–64 (same sha, board, loop, BFQ and diagnostics). They
  are compared with run 65, never pooled with it. Batch-6 figures come from the committed
  [`batch6-metrics.txt`](batch6-metrics.txt); batch-5 figures from `metrics.py` run fresh over
  [`batch5-summary.txt`](batch5-summary.txt)'s records (batch 5 has no committed per-run metrics
  file of its own).
- **Verified in source (6.12.93 work-shared tree):**
  - `bcm2835_wdt` `timeleft` truncates to whole seconds;
  - `max_hw_heartbeat_ms` is set and `max_timeout` is not;
  - `__wait_on_buffer` is `TASK_UNINTERRUPTIBLE`;
  - the sdhost 10 s per-command software timer.
- **Not verified:**
  - systemd 255's ping rule (no earlier than T/4, at the latest T/2). Its source was removed by
    rm_work; the 6.4–7.7 s intervals measured here are consistent with it;
  - the watchdog's tick rate against uptime, carried as k ∈ [1.00, 1.08];
  - that console printk reaches ramoops synchronously (it is consistent with identical pstore and
    host lines up to the last one);
  - the soft-lockup and RCU-stall knobs on this image.
