# Reset 7 analysis: batch-8 run 6 (#245 mid-install hard reset, first reset under the soft-lockup detector)

Bench board only, read-only. Nothing on the board was changed: no reboot, no install, no mount, no
/boot write, no sysctl write, no pstore access (`loop8.sh` had already copied and unmounted it; it
is still unmounted, `grep -c pstore /proc/mounts` = 0). Prod was not contacted. `~/meta-wisekiosk`'s
git state was not touched. There was one board session, at 03:02:16–03:02:22 host:
`flock -o -w 900 ~/wisekiosk-bench/records/lock ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@<BENCH_ADDRESS> sh -s < reset7-remote-read.sh`,
with each output line stamped on the host as it arrived. Address, hostname, MAC and machine-id are
written here as `<BENCH_ADDRESS>`, `<BENCH_HOSTNAME>`, `<BOARD_MAC>` and `<KIOSK_MACHINE_ID>`.

- **Record.** `records/20261102T074924Z`, test commit `375fd0328152`, `exit_status` 90.
  `loop8/summary.txt`: `02:58:14 run=6 … exit=2 record=records/20261102T074924Z reset=yes panic=no`.
  Runs 1–5 were clean.
- **Arming.** `loop8/LOG` holds 6 `kernel.watchdog_thresh = 3` readbacks, one per run, and no
  `FAIL`. The arming reached the boot that reset (boot −1, printk zero board 02:44:41.066):
  - the loop runs `set_lockup_thresh`, then the hung-task sysctls, then `hb245`, in that order,
    under `set -e`;
  - the hung-task arming took effect in boot −1, because pstore has 17 `blocked for more than 10
    seconds`… reports at 2 s spacing;
  - `hb245` ran unbroken in boot −1 from printk 184.15 (board 02:47:45, after run 5's summary
    line at 02:47:38) up to the stop.
- **pstore copy.** `pstore/console-ramoops-0`, 907 lines, md5 `0ef98d9ae6731425a416b42199327474`.
  It is the only file: **no `dmesg-ramoops-*`.**
- **Scripts and raw outputs** are in
  `/tmp/claude-1000/-home-tjwise-meta-wisekiosk/3d372d54-7280-4f07-9aa9-116c6be4bdbd/scratchpad/reset7/`:
  `reset7-remote-read.sh` → `reset7-remote-read.out` (unredacted), `final30.py` → `final30.out`,
  `timing7.py` → `timing7.out` and `detect7.py` → `detect7.out`. The committed `metrics.py`
  and `progress.py` were run over all 6 batch-8 records. `stdout.redacted` is the only
  redacted file.
- **Clocks.** Times are host EST unless marked *board* or *printk*.
  - Host = board + 0.015 s. This is the minimum of receive time minus board stamp over the 262
    `[kernel]` heartbeat lines, so it includes the latency floor.
  - printk ↔ board: the last heartbeat `[511.396082]` is board 02:53:12.462277.

## Verdict

1. **This reset is not reset 5's geometry, and that difference decides what the detector could
   show.**
   - Reset 5: PID1 petted once more and the board stopped ~0.5 s later, so the board was silent
     for ~13.5 s before the watchdog fired.
   - Reset 7: the timing test says **no further pet** after P ∈ [504.72, 505.12] printk. The
     board stopped in the ~1.2 s before the next pet was due, so the hardware watchdog fired only
     **~6.5–7.7 s after the stop** (k = 1; at most 8.4 s for k ≤ 1.08).
2. **The pstore console record holds no soft-lockup, `BUG:`, panic, RCU or watchdog line near the
   end, and no `dmesg-ramoops` file exists.**
   - The last line is an ordinary heartbeat: `[511.396] … wdt=7 p1=S p1wchan=do_epoll_wait`.
   - The only hung-task reports are the routine `mmc_rescan` claim-host waits. Every batch-8 clean
     run shows them too: 28–47 per run, against 17 here. The last one is at [498.6], 12.8 s
     before the stop.
3. **The detector was live** on that kernel (verified on the current boot, which runs the same
   slot-B kernel), and its panic path is configured to leave a `dmesg-ramoops` record.
4. **But at `watchdog_thresh=3` the detector needed 6.0–8.4 s after the stop to fire, plus
   printing and dump time. That is as long as or longer than the window this reset gave it.**
   - Modelled probability that a soft lockup would have left a dmesg record before the reset:
     **≈ 0.3–0.7**.
   - So the silence is **weak** evidence against "the kernel was looping with interrupts on",
     with a likelihood ratio of only ~1.4–3.7.
   - The hung-task detector (10 s) and the sdhost 10 s timer could not have fired in a 6.5–7.7 s
     window either. **In this reset no kernel witness had time to speak.** This event is less
     informative than reset 5.
5. **The README's batch-8 premise, "6 s threshold, under the 14 s hardware watchdog", is wrong as
   stated.**
   - The 14 s runs from the last *pet*, not from the stop.
   - The stop-to-reset window is 14 s minus the stop's phase in the pet cycle: anywhere from
     ~6.3 s to 14 s.
   - At thresh=3 the detector covers only stops in roughly the first ~5 s after a pet (~70% of
     phases). This reset fell in the uncovered part.

## 1. Final heartbeats (pstore and host `[kernel]` stream)

**pstore and host agree exactly.** Each holds 262 heartbeats, and the set difference is empty in
both directions. pstore holds **nothing after** `[511.396082] hb245 511.16`.

In the table, dR is reads completed and dWs is write sectors, both deltas since the previous
heartbeat. `p1majflt` is 143 in every row.

| host recv | printk | wdt | p1 | p1wchan | load1 | Dirty kB | WB kB | dR | dWs |
|---|---|---|---|---|---|---|---|---|---|
| 02:52:59.736 | 498.655 | 13 | S | do_epoll_wait | 4.92 | 5128 | 20252 | 0 | 35840 |
| 02:53:00.948 | 499.857 | 11 | S | do_epoll_wait | 4.92 | 6152 | 4380 | 1 | 31744 |
| 02:53:02.293 | 501.196 | 10 | S | do_epoll_wait | 4.92 | 28768 | 0 | 1 | 8896 |
| 02:53:03.528 | 502.441 | 9 | S | do_epoll_wait | 4.93 | 39092 | 6148 | 0 | 32144 |
| 02:53:04.788 | 503.696 | 8 | S | do_epoll_wait | 4.93 | 8436 | 36420 | 0 | 43064 |
| 02:53:06.320 | 505.231 | 13 | S | do_epoll_wait | 4.93 | 9724 | 35408 | 0 | 35840 |
| 02:53:07.656 | 506.556 | 12 | S | do_epoll_wait | 5.01 | 5140 | 40540 | 0 | 38912 |
| 02:53:08.769 | 507.684 | 11 | S | do_epoll_wait | 5.01 | 6176 | 40036 | 0 | 32768 |
| 02:53:09.898 | 508.807 | 10 | S | do_epoll_wait | 5.01 | 6184 | 19556 | 0 | 39936 |
| 02:53:11.208 | 510.124 | 8 | S | do_epoll_wait | 5.01 | 18620 | 4100 | 1 | 31952 |
| **02:53:12.490** | **511.396** | **7** | **S** | **do_epoll_wait** | 4.85 | 40740 | 3176 | 0 | 29736 |

The full 30-row table is in `final30.out`.

- **wdt and PID1.**
  - Pets fall at the 13s ([477.0], [484.7], [490.9], [498.7], [505.2]), at the healthy 6.2–7.7 s
    spacing.
  - The last reading, 7, is the healthy pre-pet floor. `metrics.py` gives `min_wdt=7` for all 6
    batch-8 runs.
  - PID1 was `S do_epoll_wait` in every heartbeat (one `R`), with `p1_d_seconds=0.0`. It was never
    in `D`.
- **Load** was 4.85 at the end and 5.01 at most in the window. Healthy batch-8 window maxima are
  5.03–7.79 (n = 5), so the load was on the low side.
- **Dirty/Writeback.** The last row (40.7 MB Dirty, 3.2 MB WB) is routine. Every healthy batch-8
  run has 3–8 heartbeats with Dirty ≥ 40 MB and WB ≤ 4 MB, and their maxima are 47.9–50.8 MB.
  **No precursor.**
- **Copy progress.**
  - The last rauc line was ` 77% Copying image to rootfs.0`.
  - 2 367 418 sectors were written by +125.4 s after `capture started`. That is ~56% of the
    image's bytes; a full copy is ~4.21 M sectors.
  - The healthy batch-8 runs reach the same volume at 122.4–129.9 s (n = 5), so the run was **on
    schedule**.
- **uv** was 0 in every sample. `freq=900000` throughout.
- **Host side.** The last `[journal]` data arrived at 02:53:11.507, the last `[stats]` at
  02:53:12.266 and the last `[kernel]` at 02:53:12.490.
  - The three sessions logged `not responding` 7.48, 7.73 and 7.51 s later. That is the
    ServerAlive signature, as in resets 2–5.
  - The `[stats]` sample due at ~02:53:13.4–13.7 never arrived.
  - The last line's latency was 0.028 s, which is normal: no sluggishness before the stop.
- **Soak** last ran in boot −1 at 02:49:41–43, and the next run was due ~02:54:41. It was not
  running at the stop.

## 2. Detector strings in pstore, and was the detector live

**pstore console** (case-insensitive grep for `soft lockup|BUG:|Kernel panic|rcu|watchdog|hung`):
- **No match near the end.** The only matches are boot-time lines:
  - two `RCU Tasks … Setting shift` lines;
  - `bcm2835-wdt … watchdog timer`;
  - systemd's `Using hardware watchdog … 14s`;
  - `mmc_debug` (a false hit on "BUG").
- `hung_task` lines are the 17 routine `mmc_rescan` reports (§1). The last is `[498.615] … blocked
  for more than 43 seconds`, and then the task got the host claim.
- **No RCU stall line is possible here.** `CONFIG_TINY_RCU=y` has no stall detector, so the
  absence of "rcu" says nothing.

**Was the detector live on the boot that reset?** Yes, by the following chain:
- **Same kernel.** The current boot is slot B (rootfs.1), which is also what boot −1 ran: rauc
  reports `Active slot bootname: 'B'` at install start, and the install target was rootfs.0. The
  current-boot readback therefore reads the same kernel image.
- **Current boot, read-only:**
  - `watchdog=1`, `soft_watchdog=1`, `softlockup_panic=1`, `watchdog_cpumask=0` (CPU 0 in list
    format), `nmi_watchdog=0` (no hard-lockup detector, as expected on ARMv6 UP);
  - `watchdog_thresh=10`. **It reverted to the default at reboot**; the loop writes 3 again before
    each run.
  - `soft_watchdog` and `softlockup_panic` exist only with `CONFIG_SOFTLOCKUP_DETECTOR`, and both
    are present.
  - The cmdline has no `nowatchdog`, `nosoftlockup`, `watchdog_thresh=` or `softlockup_panic=`, and
    neither does boot −1's cmdline in pstore.
- **Built config** (`build/tmp-raspberrypi0-wifi/work/…/linux-raspberrypi/6.12.93+git/…/.config`,
  mtime 00:53 today): `CONFIG_LOCKUP_DETECTOR=y`, `CONFIG_SOFTLOCKUP_DETECTOR=y`,
  `CONFIG_BOOTPARAM_SOFTLOCKUP_PANIC=y`.
- **Boot −1** got `watchdog_thresh=3` (see Arming, above).
- **`dmesg | grep -i watchdog` shows no detector boot message, and none is expected.**
  - In 6.12.93, `lockup_detector_init()` prints only for nohz_full or for a failed hard-lockup
    retry.
  - The retry is scheduled only from `drivers/perf/arm_pmuv3.c` (ARMv8). Checked in source.
  - The lines present are `bcm2835-wdt` and systemd's hardware-watchdog lines.

**Is the panic path plausible?** Yes, as configured (from source and current-boot values; not
exercised, see §5):
- `softlockup_panic=1`, so `watchdog_timer_fn` prints `BUG: soft lockup - CPU#0 stuck for Ns!`
  plus registers, then `panic("softlockup: hung tasks")`.
- panic → `kmsg_dump(KMSG_DUMP_PANIC)`. ramoops has `record_size=32768` and `max_reason=2`
  (≥ PANIC=1, OOPS=2), so a `dmesg-ramoops-*` record would be written.
- Also on the board: `panic=10` (cmdline) and `panic_on_oops=1`.
  - With `panic=10` the kernel would restart 10 s after panicking. That is at least the stop +
    16 s, always later than the hardware watchdog (at most the stop + 14 s), so the watchdog
    resets the board either way.
  - The kernel restart path (`bcm2835` restart handler, a watchdog full reset) would also give
    RSTS 0x20. **RSTS cannot tell a panic-reboot from a watchdog expiry; only the dmesg record
    can.**

## 3. Did the detector have time? (the timing)

**Clocks.**
- **Kernel start of the current boot, K = 02:53:27.567 host.** This is the minimum of
  host-receive minus `/proc/uptime` over 20 samples (spread 0.23 s).
  - Cross-check: `dmesg --time-format iso` head board 02:53:27.554542, plus the offset, gives
    02:53:27.569 (Δ 3 ms).
  - Last heartbeat to K: **15.09 s.** Earlier resets: reset 5 22.04, reset 4 7.65, reset 3 17.34.
- **F, measured fresh.** Boot −2 `Journal stopped` (board 02:44:33.680) to boot −1 printk zero
  (02:44:41.066) is **7.386 s**. That is inside the 7.32–7.43 s envelope (now n = 17). B ≤ F.
- **Observed reset (K − B, tail ~0):** printk **519.06–519.17**, host 02:53:20.14–20.25.

**Watchdog timing test** (the `timing.py` method; `timing7.out`):

| scenario | k = 1.00 | k = 1.08 |
|---|---|---|
| last pet P (wdt bounds, 6 samples) | 504.72–505.12 | 504.40–504.72 |
| A: no further pet, reset at P + 14k | 518.72–519.12, **miss 0** | 519.52–519.84, miss 0 |
| B: one more pet after the last heartbeat | ≥ 525.16, **miss −5.0 s** | ≥ 526.28, miss −6.1 s |

- **A fits, with a near-zero shutdown tail. B is rejected**: it would need a reset-to-kernel time
  of ≤ 1.3 s, against F = 7.4 s.
- An immediate reset at the stop (reset 4's shape) would need B ≈ 14–15 s, and is rejected too.
- A soft-lockup panic followed by the `panic=10` restart would put the reset at ≥ S + 16 s, and is
  rejected.
- **The reset agent is the hardware watchdog, expiring 14 s after the pet at ~505.** That is
  consistent with RSTS 0x20.

**The stop window.**
- **Alive:** the board was alive at printk 511.396 (heartbeat printed, PID1 `S do_epoll_wait`).
- **Silent after:** the next pet was due by P + 6.4…7.7 ≈ 511.1–512.8 and never reached the
  hardware. The next `[stats]` (≈ 512.3–512.6) and the next heartbeat (≈ 512.5–512.9) never came.
- So **S ∈ [511.40, ~512.6]** and **stop → reset = 6.5–7.7 s** (k = 1), or up to 8.4 s
  (k = 1.08).

**Detector latency at `watchdog_thresh=3`** (from `kernel/watchdog.c`, 6.12.93; `detect7.py`):
- **Mechanism.**
  - The hrtimer fires every `sample_period` = 2·3/5 = **1.2 s** and queues the touch.
  - On UP, `stop_one_cpu_nowait` is `schedule_work`, an ordinary `system_wq` kworker. Checked in
    `include/linux/stop_machine.h`.
  - The touch stores `sched_clock >> 30`, in units of 1.074 s.
  - A tick reports when `floor(now/u) > floor(touch/u) + 6`. Ticks land at touch + n·1.2 s, so the
    report comes at touch + 7.2 s (~70% of phases) or touch + 8.4 s.
- **Latency after the stop: 6.0–8.4 s (median 6.8)**, before any printing or the deflate +
  ramoops write.
- **Modelled P(dmesg record lands before the reset)**, with S uniform in its window and a uniform
  hrtimer phase:

  | | dump time 0 | dump time 0.5 s |
  |---|---|---|
  | R at k = 1 | 0.59 | 0.27 |
  | R over k ∈ [1, 1.08] | 0.73 | 0.50 |

  - The dump time is an assumption. It is not measured, and `console=tty1` (fbcon) printing could
    lengthen it.
  - Under reset 5's geometry, the same model gives **1.00**.

**Answer to Q3: no, not reliably.** The window was about the detector's own latency, so it may
have been on the way to firing when the watchdog won.

## 4. Current boot (read 03:02:16 host)

- **RSTS:** `rsts: 00000020`, `partition: 0`, `tryboot: 0`, `boot-mode: 1`.
  - HADWRF (watchdog full reset) is the only bit set; HADPOR is clear (decode per
    `reset2-rsts-pstore.md` §1).
  - **6 of 6** across resets 2–7.
  - As noted in §2, a kernel panic-restart would also set HADWRF.
- **uv:** `hwmon1 in0_lcrit_alarm=0`. No voltage or throttle line in dmesg. Thermal 38.5 °C.
- **rauc status.**
  - Booted `rootfs.1 (B)`, Activated `rootfs.1 (B)`.
  - `[rootfs.1]` (/dev/mmcblk0p3) booted and **good**. `[rootfs.0]` (/dev/mmcblk0p2) inactive
    and **bad**: the interrupted target.
  - `fw_printenv`: `BOOT_ORDER=B`, `BOOT_A_LEFT=0`, `BOOT_B_LEFT=3`. **The fallback worked as
    designed.**
- **Other state.**
  - Scheduler `none [mq-deadline] kyber bfq`, governor `ondemand`.
  - Hung-task sysctls are back at their defaults (120 / 0 / 10). `hb245` processes: 0.
  - watchdog0: `timeout=14`, `timeleft=12`, `bootstatus=0`. `RuntimeWatchdogUSec=14s`.
  - `tainted=0`.
- **dmesg.**
  - `EXT4-fs (mmcblk0p3): recovery required … recovery complete`: boot −1's root journal was
    replayed.
  - `FAT-fs (mmcblk0p1): Volume was not properly unmounted` at [14.55], /boot's dirty bit as in
    resets 4–5. Neither of these is a write I made.
- **Journal.** Boot −1 runs 02:44:35 → 02:53:03. The on-disk journal ends at heartbeat 502.23,
  ~9 s before the stop, which is ordinary flush lag. There are no non-heartbeat lines after the
  install's start, apart from rauc, sshd and audit.

## 5. Verdict detail

**What "no soft-lockup panic" rules out here: little, and only weakly.**
- The brief's premise, "≥ 6 s of stop before the 14 s HW watchdog", holds only nominally. The stop
  gave **6.5–7.7 s**, and the detector needs **6.0–8.4 s plus dump time**.
- If the kernel had been looping with interrupts on, a record would have appeared with probability
  only ~0.3–0.7.
- Likelihood ratio for "no record": ~1.4–3.7 in favour of "not an interrupts-on loop".

**What the silence does not discriminate, in this reset:**
- **Interrupts-off hang in a driver.** A `spin_lock_irqsave` region that never exits, or a register
  poll with IRQs off. The hrtimer never fires, and nothing can print.
- **Bus/SoC hang.** The ARM1176 stalls on a peripheral access that never completes (AXI), or
  there is a clock/SDRAM fault. Silent by construction.
- **Interrupts-on CPU loop.** The detector was racing the watchdog (§3), so this is not excluded.
- **A userspace-only stall.** PID1, the heartbeat and the stats ssh all stop while the kernel
  lives. In reset 5 this was argued against by 14 s of hung-task and sdhost silence. Here both
  10 s witnesses were cut off at ~7 s, so **nothing in reset 7 excludes it**.
- **Power.** `uv=0` throughout and HADPOR clear argue against a brownout. This is only as strong
  as the 1–1.3 s sampling of the uv flag.

**Weak, post-hoc observation (not a finding).**
- In both resets with the wdt heartbeat (5 and 7), the stop is within ~1.3 s of a pet: ~0.5 s
  after one in reset 5, just before a due one here.
- Under a uniform-phase model that is roughly p ≈ 0.02, but the statistic was chosen after
  seeing the data, and n = 2.
- A pet is `ioctl` → `bcm2835_wdt_start`, which writes PM_WDOG/PM_RSTC under
  `spin_lock_irqsave`. A hang inside it would be interrupts-off, silent, and would leave the old
  pet's timer running, which is exactly reset 7's timing.
- Reset 5's "pet completed, then stopped 0.4–0.7 s later" does not fit that at k = 1.
- I note it as a hypothesis the data permits. I am not proposing it.

**The panic path itself is unproven on this board.**
- Nothing has shown that the detector fires → `BUG:` reaches the pstore console → `panic` →
  `dmesg-ramoops` lands, before the watchdog, on this hardware.
- **Test modules: none.** `.config` has `# CONFIG_TEST_LOCKUP is not set` and `# CONFIG_LKDTM is
  not set`. Of 1 774 modules in `/lib/modules/6.12.93`, none is `lkdtm` or `test_lockup`; the
  only `test` hit is `usbtest.ko`. There is no `/proc/config.gz`.
- **In-image seeds that exist. Reported, not triggered; the owner's call; bench only.** All are
  runtime-only and recover by reboot. Each one panics or resets the board.
  - **Panic → pstore half: `echo c > /proc/sysrq-trigger`.**
    - `sysrq_handle_crash` calls `panic("sysrq triggered crash")`.
    - `/proc/sysrq-trigger` ignores the `sysrq=16` mask (`__handle_sysrq(c, false)`). Checked in
      source.
    - It proves kmsg_dump → `dmesg-ramoops`, then the `panic=10` restart. It does not prove
      detection.
  - **Detection half, with no module, via CFS starvation.**
    - On UP the touch is an ordinary kworker. Starving CFS for more than 6 s should trip the
      detector.
    - That needs both of these, since 6.12.93 has the fair-server dl_server, which otherwise gives
      CFS 50 ms/s:
      - `sched_rt_runtime_us=-1`, currently 950000;
      - the fair server disabled: `/sys/kernel/debug/sched/fair_server/cpu0/runtime` = 0. Its write
        handler accepts 0 and prints "Fair server disabled…". `CONFIG_SCHED_DEBUG=y`.
    - Then a `chrt -f 99` busy loop.
    - **Unverified:** that this starves the kworker in practice. Debugfs mount state was not read.
- **Class.** Both are **recoverable over the wire**: a kernel panic or a watchdog reset into the
  same booted slot, with no install in flight. Neither touches /boot, slots or the keyring.

**Lean, a decision for the owner: make the detector able to win the race before counting more
resets.**
- `watchdog_thresh=1` gives a 2 s threshold and a 0.4 s sample. Worst-case detection after the
  stop is **3.6 s**, inside the minimum ~6.3 s window with ~2.7 s of margin, at every pet phase.
- `watchdog_thresh=2` gives at most 5.6 s plus dump time against a 6.3 s minimum, which is too
  thin.
- **Cost and risk.**
  - On UP the touch is a SCHED_NORMAL kworker, so any ≥ 2.1 s CPU starvation of CFS during an
    install would panic the board: a false "reset", but one carrying a `BUG:` stack, so it can
    be told apart.
  - The 5 clean batch-8 runs show no false positive at 6 s (load up to 7.8), which says nothing
    about 2 s.
  - Class: a runtime sysctl, recoverable, reverts at reboot.
  - It is a one-word change to `loop8.sh`'s `set_lockup_thresh`, which is a tracked file, so it is
    the owner's call.
- **The sysrq `c` seed** would close the "panic path unproven" caveat at the cost of one bench
  panic.

## Classes and revert

- **Board changes: none, so there is nothing to revert.**
  - The one session ran only `cat` of /proc and /sys, `hexdump` of /proc/device-tree, `dmesg`,
    `journalctl`, `ps`, `ls`/`find` of /lib/modules, `rauc status`, `fw_printenv`,
    `systemctl show` and `uname`/`date`.
  - pstore was not mounted, and nothing was deleted.
- **Host side**, I wrote only `scratchpad/reset7/*` and this file.

## Measurement notes

- **Board sessions:** 1. RSTS was read once (n = 1 this reset; 6 of 6 across resets 2–7).
- **K:** 20 host-stamped uptime samples, using the minimum-latency estimator, cross-checked
  against the dmesg head (Δ 3 ms).
- **F:** n = 17 warm reboots, 7.32–7.43 s. The shutdown tail is unmeasured, and only B ≤ F is
  used.
- **Healthy comparison:** batch-8 runs 1–5 (same sha, board and loop; mq-deadline). They are
  compared with run 6 and never pooled with it.
- **Verified in source (6.12.93 work-shared tree):**
  - the softlockup sample period, units and report condition;
  - `softlockup_panic` defaults from `CONFIG_BOOTPARAM_SOFTLOCKUP_PANIC`;
  - UP `stop_one_cpu_nowait` = `schedule_work`;
  - no detector boot message on arm32;
  - the kmsg_dump reason enum;
  - sysrq `c` = panic, and the trigger file bypasses the mask;
  - the fair-server runtime write accepts 0.
- **Not verified:**
  - that the detector → panic → dmesg path completes on this board;
  - the dump/print time;
  - the watchdog tick scale (k ∈ [1.00, 1.08] carried);
  - systemd's pet rule (the 6.2–7.7 s intervals are measured);
  - the CFS-starvation seed's behaviour.
- **Model inputs:** S is taken as uniform over its window. The dump time is assumed (0 or 0.5 s).
  The P values in §3 are model outputs, not measurements.
