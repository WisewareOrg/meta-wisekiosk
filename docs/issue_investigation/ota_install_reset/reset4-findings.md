# Reset 4 analysis: batch-4 loop run 25 (#245 mid-install hard reset, governor pinned)

Bench board only, read-only. I changed nothing on the board: no reboot, no install, no mount, no
/boot write, no pstore access (pstore was not mounted; `loop4.sh` had already copied and unmounted
it), no sysctl, no debugfs or sysfs write. Prod was not contacted. `~/meta-wisekiosk`'s git state
was not touched (branch `245-ota-log-capture`, clean). There were two board sessions, each a single
`flock -o -w 900 ~/wisekiosk-bench/records/lock ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 root@<addr> sh -s < script`.
In this file the address, hostname, MAC and machine-id appear as `<addr>`, `<host>`, `<mac>` and
`<machine-id>`.

- **Record.** `records/20261031T121511Z`, sha `3cb4f4cc0453`. The loop summary line is
  `2026-10-31T08:25:34-0400 run=25 sha=3cb4f4cc…906289 exit=2 record=records/20261031T121511Z reset=yes`.
  Runs 1–24 of batch 4 were clean, so this is the first reset in 25 runs.
- **pstore copy.** `records/20261031T121511Z/pstore/console-ramoops-0`, 103 428 B, 929 lines, md5
  `9da1a586250410bbfdf345b528b18fcb`. It is the only file. Its kernel command line carries `<mac>`,
  so scrub it before it goes anywhere tracked.
- **Scripts:** `extract.py`, `window.py` and `episodes.py` are the committed reset-3 scripts,
  reused as-is except `episodes.py`'s `S=` path, repointed at `loop4/summary.txt` for this
  reset (not committed separately: a one-line path edit, not a different script). `batch4.py`
  (committed), a per-run summary of all 25 batch-4 runs. `endphase.py <runs…>` (committed),
  the per-sample end-of-copy phase. `reset4-remote-read.sh` and `reset4-remote-read2.sh`
  (committed, renamed from `remote-read.sh`/`remote-read2.sh` to avoid colliding with reset 3's
  same-named scripts already in this directory) were each run once over ssh. Their raw `.out`
  outputs were unredacted and are not committed; the redacted excerpts are
  `reset4-host-tail.log` and `reset4-console-ramoops-tail.log`.
- **Clocks.** Times are **host** time (`-0400`) unless marked *board*.
  - Host = board + 0.029 s. This is the minimum of host-receive minus board-stamp over all 338
    `[kernel]` heartbeat lines, so it includes the latency floor.
  - Boot −1's printk zero is board 08:10:26.7528. It comes from `[609.136464]`, which is board
    08:20:35.889264 on the same line in the `[kernel]` stream.

## Verdict

1. **The CPU frequency was 900000 kHz in every heartbeat, with no other value.** That holds for
   all 338 lines in pstore, the same 338 in the host `[kernel]` stream, and the 155 that reached
   the `[journal]` stream. The last one is `[609.136] … freq=900000`, the final line of the
   record.
2. **This reset does not fit the reset-2/3 picture of a freeze followed by the watchdog.**
   - The next kernel started **7.648 s** after the last heartbeat (host clock, ±0.01 s).
   - The warm-reboot path from "Journal stopped" to kernel start takes 7.32–7.43 s on this board
     (n = 14 in batch 2, plus one fresh sample today of 7.385 s, so n = 15).
   - So the time from the last heartbeat to the reset is **R ≈ 0.26 s plus the shutdown tail**,
     and at most ~2.3 s for any plausible tail. Reset 3 had R ≥ 9.4 s and reset 2 had R ≥ 10.7 s.
   - A freeze followed by the hardware watchdog needs **R ≥ 7 s**: the timeout is 14 s and
     systemd pets every 7 s. To get there, firmware plus u-boot would have to take ≤ 0.65 s.
   - In this reset the board was running, with the heartbeat at a 1.23 s cadence and writes
     completing at 10–20 MB/s, until **at most ~2 s before it reset**. With a sub-second tail, the
     reset came before the next heartbeat was due.
3. **DVFS.** Frequency switching requested by the kernel is **not necessary for the reset: strong**
   (§4). Most of what was still consistent survives. The new timing also moves weight away from a
   SoC or bus lockup and towards something that **resets a live board** (§4).

## 1. Host-side timeline

The capture markers in stderr:

    2026-10-31T08:17:07.807130-0400 capture started
    2026-10-31T08:20:42.505428-0400 [journal] session ended
    2026-10-31T08:20:43.505473-0400 [stats] session ended
    2026-10-31T08:20:43.505559-0400 [kernel] session ended
    Read from remote host <addr>: Connection reset by peer      (unstamped: the rauc-install ssh)
    client_loop: send disconnect: Broken pipe                   (unstamped)
    2026-10-31T08:25:31.798241-0400 capture stopped
    error: recipe `kiosk-install` failed on line 235 with exit code 255

The last real line of each stream:

    08:20:32.946034 [journal] … <host> unknown: hb245 605.52 … uv=0 freq=900000            (journal lags ~3 s, as usual)
    08:20:35.925704 [kernel]  2026-10-31T08:20:35,889264-04:00 hb245 609.02 MemFree:45576 Dirty:0 Writeback:17232 load=7.29 4.33 2.09 mmc=5271 565 627638 180000 6045 520972 4441140 9377719 0 157910 9557720 0 0 0 0 0 0 uv=0 freq=900000
    08:20:35.977345 [stats]   MemFree:45576 Dirty:0 Writeback:15696 load=7.29 4.33 2.09 mmc=5271 565 627638 180000 6048 520972 4444212 9385904 0 158000 9565905 0 0 0 0 0 0 uv=0

- **The `[stats]` sample was taken after the last heartbeat.** Its write-sector counter is 3072
  sectors (1.5 MB) further on, about 0.1 s of writing at the observed rate. So the last sign of
  life is board ≈ [609.19–609.24], host ≈ 08:20:35.98.
- The sessions dropped 6.53 s and 7.53 s after the last line. That is the same
  `ServerAliveInterval=2 ServerAliveCountMax=3` signature and the same 1 s split as resets 2 and 3.
- **Where the copy had got to.**
  - The last rauc line was ` 99% Copying image to rootfs.0`, stamped at about +204.7 s. The last
    sign of life was at +208.2 s.
  - In bytes, 4 177 418 sectors had been written since the first `[stats]` sample. That is
    **99.26 %** of the healthy batch-4 median of 4 208 596 (n = 24, range 4 206 250–4 213 329).
  - Writeback still held 15 696 kB (31 392 sectors), and adding it gives 100.01 %. **Every byte
    of the image had been handed to the block layer.** `Dirty` was 0, and the reset fell in the
    final writeback flush, the last ~1–2 s before `Copying image … done`.
  - Healthy runs pass through the same state: run 10 at +186.0 had Dirty 380 and WB 4524, and run
    21 at +210.6 had Dirty 268 and WB 14352. So the state itself is ordinary.
- **Cadence.**
  - `[stats]`: 168 samples, mean interval 1.224 s. The only gap over 1.6 s is 2.02 s at +22.9 s,
    the routine install-start stall, much smaller than reset 3's 8.8 s.
  - Heartbeat: 338 lines, mean interval 1.253 s. Gaps over 1.6 s (1.6–2.5 s) occur only at
    [409]–[426], the install start. The last 20 intervals have a mean of 1.233 s and a max of
    1.364 s.

**The last 30 s of `[stats]`** (`window.py`; the table below is the full final-30-seconds
window, not an excerpt of a longer one):

| host | MemFree | Dirty | WB | load1 | MB/s |
|---|---|---|---|---|---|
| 08:20:06.0 | 49544 | 6656 | 37448 | 5.82 | |
| 08:20:13.5 | 46340 | 4524 | 41756 | 6.25 | 14.0 |
| 08:20:21.8 | 47156 | 21272 | 19708 | 6.47 | 16.1 |
| 08:20:24.4 | 47708 | 43848 | 76 | 6.91 | 8.9 |
| 08:20:29.2 | 52856 | 3924 | 38500 | 7.32 | 17.1 |
| 08:20:32.6 | 48228 | 9320 | 32008 | 7.32 | 17.2 |
| 08:20:33.8 | 44016 | 7664 | 34528 | 7.29 | 12.5 |
| 08:20:34.9 | 47436 | 3560 | 31464 | 7.29 | 9.8 |
| 08:20:36.0 | 45576 | 0 | 15696 | 7.29 | 19.6 |

**What is new in the final 30 s, and whether it is new against healthy runs** (`batch4.py`,
`endphase.py`):
- **Load reached 7.32.** That is the highest of the 25 runs at 99% (healthy 4.33–7.08, n = 19
  with a sample). It is marginal.
- **The run was slow.** 99% came at +204.7 s against a healthy median of 192.6 s (range
  187.7–212.9). Runs 21, 23 and 24 were also 204–213 s and were clean.
- **Reads were starved behind the write queue.** In the last 5 s, 17 reads completed with 38.5 s
  of summed read ticks, so **~2.3 s per read** (5 reads/12.5 s, 8/19.9 s, 1/1.0 s, 3/5.1 s). In
  the preceding ~10 s there were no reads at all.
  - This is **not unique**. Healthy run 10 had 10 reads totalling 20.7 s in one sample during its
    copy. Most healthy runs do almost no reads until the post-copy burst of ~200 fast reads, which
    run 25 never reached.
  - It does mean that **any page-in at that moment waited ~2.3 s**, which matters in §4.
- **No precursor.** There is no throughput fall-off, no memory fall-away, and `uv` is 0
  throughout.

## 2. The pstore console record compared with the host stream

**Which boot this is.** The record starts `[0.000000] Booting Linux …` and does not wrap (103 kB
in a 128 KiB zone). It holds the install's verity audit record, `audit(1793449031.728:34)` at
[405.0]. The first heartbeat is at [186.98], board 08:13:33.73. That is 5 s after run 24's summary
line and right after run 25's `set_governor` readback, the last one in `loop4/LOG`:
`scaling_governor=performance scaling_cur_freq=900000 scaling_max_freq=900000`. No reboot came
between the governor set and the reset, because the heartbeat started by the arming step is in
this same boot.

**Does the pstore heartbeat end where the host stream ends?** **Yes, exactly.**
- The host `[kernel]` stream and pstore hold the same 338 heartbeats; `diff` of the two lists is
  empty.
- They also hold the same 14 hung-task reports.
- The record's final line is `[609.136464] hb245 609.02 … Dirty:0 Writeback:17232 … uv=0 freq=900000`,
  which is the host's last `[kernel]` line.
- Nothing was printed after it: no heartbeat, no oops, no `reboot: Restarting system`, no
  `Kernel panic`, no `sysrq`, no mmc, sdhost, brcmfmac, RCU or OOM line.
- There is no `dmesg-ramoops-*` file.

**Hung-task reporter cadence.** There were 14 reports in 4 episodes, all `events_freezable mmc_rescan`
blocked in `__mmc_claim_host` ← `mmc_sd_detect`:
- `kworker/0:2:35`: 10–14 s at [524.6]–[528.7];
- `kworker/0:0:6`: 10–12 s at [547.4]–[549.5];
- `kworker/0:0:6`: 10–12 s at [566.2]–[568.2];
- `kworker/0:0:6`: 10–22 s at [582.8]–**[595.287]**.

Within each episode the reports are 2.075–2.086 s apart. The last episode **ended healthily**:
the next report was due at [597.37] and the kernel ran on for another 11.8 s without printing it.
**So unlike reset 3, no report was pending at the stop, and khungtaskd gives no extra bound.** The
stop is bounded by the heartbeat alone (next due ≈ [610.37]) and by the reset time (§3).

- In batch 4, 85 healthy episodes had a maximum block of 10–70 s, and run 25's 22 s is ordinary.
- **A correction to reset 3's weighting.** In batch 4, **4 of 40** episodes that reached the 18 s
  report ended exactly there, against batch 3's 1 of 59. Pooled, that is 5 of 99. Reset 3's "next
  report was due, so the kernel stopped" argument is therefore ~95 % rather than ~98 %.
- **Source fact that bears on every reset.** In this kernel's `kernel/hung_task.c`, khungtaskd
  checks only `TASK_UNINTERRUPTIBLE` tasks **without** `TASK_WAKEKILL`.
  - Page-fault reads wait killably: `filemap_fault` → `lock_folio_maybe_drop_mmap` →
    `__folio_lock_killable`, and `filemap_read_folio` → `folio_wait_locked_killable`.
  - Dirty throttling also sleeps killably: `balance_dirty_pages` → `TASK_KILLABLE`.
  - **So a process stalled on page-in or on dirty throttling never appears in a hung-task report,
    however long it waits.** The 10 s/2 s settings armed by the loop cannot see those stalls.

**Under-voltage.** `uv=0` in all 168 `[stats]` samples and all 338 heartbeats. This is the
firmware's sticky bit, which the driver polls every 2 s (reset 3 §2), so it covers up to ≤ 2 s
before [609.2].

## 3. The current boot (read 08:31:30 and 08:34:46 host)

- **Kernel start.** The `dmesg --time-format iso` head is `2026-10-31T08:20:43,536585-04:00`
  (board). In host time, 15 host-stamped `/proc/uptime` samples give the minimum of host-receive
  minus uptime as **08:20:43.566** (spread over the other samples +0.005 to +0.24, min-latency
  estimator). The two agree to 0.001 s after the 0.029 s offset. NTP reads `NTPSynchronized=yes`.
  boot_id is `2942e6af…`.
- **Last heartbeat to kernel start: 7.648 s.** Reset 3 was 17.34 s.
- **F, a fresh sample.** Boot −2's `systemd-journald: Journal stopped` was at board
  08:10:19.367979, and boot −1's kernel started at 08:10:26.7528, so **7.385 s**. That is inside
  batch 2's 7.32–7.43 s, giving n = 15. It includes the systemd-shutdown tail, so F ≤ 7.385 s on
  this path.
- **R, the freeze-to-reset time.** R = 7.648 − F, so **0.26 s plus the tail**: about 0.3–1.3 s for
  a tail of 0–1 s, and about 2.3 s for a 2 s tail. The reset instant is board ≈ [609.40 + tail],
  so if the tail is under ~1 s the reset came **before** the next heartbeat was due at [610.37].
- **Reset-cause copy.** `rsts: 00000020`, `partition: 00000000`, `tryboot: 00000000`,
  `boot-mode: 00000001`.
  - Decoded per `reset2-rsts-pstore.md` §1, **only HADWRF (bit 5, watchdog full reset) is set**;
    HADPOR is clear.
  - This is the same value as resets 2 and 3, so n = 3 across resets.
  - HADWRF means *something wrote PM_RSTC/PM_WDOG*: the hardware watchdog expiring, the kernel's
    `reboot`/panic path (which prints, and nothing printed), or possibly the VideoCore firmware.
    That last one is unverified.
  - There is still no cold-boot or brownout control reading, so how a supply event presents in
    RSTS is **unmeasured**.
- **uv now.** `/sys/class/hwmon/hwmon1 in0_lcrit_alarm=0`. No voltage or throttle line in dmesg.
  The thermal zone reads 40.6 °C (idle, current boot). There is no `vcgencmd` on the image, so
  firmware throttle bits cannot be read.
- **rauc status.**
  - Booted `rootfs.1 (B)` and Activated `rootfs.1 (B)`.
  - `[rootfs.1]` (/dev/mmcblk0p3) booted and **good**. `[rootfs.0]` (/dev/mmcblk0p2) inactive and
    **bad**, the interrupted target.
  - `fw_printenv`: `BOOT_ORDER=B`, `BOOT_A_LEFT=0`, `BOOT_B_LEFT=3`. The fallback worked as
    designed.
- **Other state.**
  - pstore mounts: 0. No hb245 process.
  - `hung_task_timeout_secs=120`, `check_interval=0`, `warnings=10` (defaults). `printk_devkmsg=on`,
    which is unexplained and harmless, as in reset 3.
  - watchdog0: `timeout=14`, `bootstatus=0`, `RuntimeWatchdogUSec=14s`, `RuntimeWatchdogPreUSec=0`,
    and `timeleft` exists and reads (11).
  - `FAT-fs (mmcblk0p1): Volume was not properly unmounted` at [14.63]. That is /boot's dirty bit
    again after an unclean reset.
  - Governor is back to `ondemand`, so the loop's change was runtime-only, as designed.

## 4. Verdict detail

**Does this reset rule out DVFS/frequency switching as the cause?**
- **Kernel-requested switching is not necessary for the reset: strong.** One reset under a fixed
  frequency is enough.
  - The governor was `performance`, read back on the same boot before the install (§2).
  - `freq=900000` is in all 338 heartbeats, right up to the last line.
  - Under `performance` the cpufreq core sets `policy->max` once and changes it only if limits
    change. Any change, including a thermal clamp, would have shown in `freq=`.
- **Caveat 1: what `freq=` measures.**
  - `scaling_cur_freq` on this kernel is `policy->cur`, the kernel's record of the last frequency
    it **requested**. It is not a hardware read (`cpufreq.c` `show_scaling_cur_freq`;
    `arch_freq_get_on_cpu` is 0 on ARM32, and `cpufreq-dt` has no `setpolicy`).
  - `cpuinfo_cur_freq` would query the firmware (`cpufreq_generic_get` → `clk_get_rate`, with
    `CLK_GET_RATE_NOCACHE`).
  - So firmware-side throttling would be invisible to `freq=`. Its under-voltage trigger is
    excluded to ≤ 2 s before the stop by `uv=0`. The temperature trigger is unmeasured in boot −1.
- **Caveat 2: half of the fix is untested.** Only the fixed-frequency half of
  raspberrypi/linux#2555's remedy was tested. `over_voltage` was not, and that is a /boot change,
  so hands-on class.
- **Caveat 3: rate.** 1 reset in 25 runs here against 1 in 35 in batch 3, with n = 1 each. The
  data cannot say whether DVFS changes the **rate**, only that it is not required.
- **Caveat 4: the lever may have changed little.** Batch 3 had no `freq=` field, so it is unknown
  how much `ondemand` actually switched during an install at load 5–7. `performance` may have
  changed little in that window. It still makes the claim above sound, because switching was
  provably absent here.

**The new timing finding (§3) re-weights the remaining candidates:**

| candidate | predicts | reset 4 | strength |
|---|---|---|---|
| SoC/CPU/bus lockup, then the 14 s hardware watchdog (resets 2/3's best fit) | a silent gap R of 7–14 s before the reset | R ≈ 0.26 s + tail (≤ ~2.3 s) | **Disfavoured for this reset, strong.** It needs F ≤ 0.65 s against the 7.32–7.43 s measured (n = 15) |
| SD-card-induced bus hang (a stuck AXI/peripheral access stalling the core) | the same as a lockup: silence, then the watchdog 7–14 s later | as above | **Disfavoured as the proximate event, strong.** SD *congestion* is present (reads ~2.3 s each) and may be an enabler |
| WiFi SDIO + SD concurrency (bus-level) | a lockup signature, or an SDIO error | no SDIO or brcmfmac error; same timing objection | **Disfavoured as a lockup cause. Undecided** as a load contributor |
| **Hardware watchdog firing on a live kernel**: PID1, the only pet source, stopped petting ~14 s before the reset (≈ [595.4–597.4]) while the kernel, the heartbeat and I/O ran on | RSTS 0x20, nothing printed, the heartbeat running to the reset, no hung-task report (a killable page-in wait is invisible, §2) | all four hold. Page-ins were taking ~2.3 s each at the end, so a handful of sequential faults would exceed 14 s | **Consistent, not measured.** No direct evidence that PID1 stalled. It would also explain reset 3/2's R only if userspace as a whole stalled first |
| **Supply margin**: a dip that resets the SoC at once | the board alive until the reset, R ≈ 0, nothing printed | fits the timing well. `uv=0` covers to ≤ 2 s before, and a fast dip can fall between polls. RSTS 0x20 rather than 0x1000 argues against, but how a brownout presents is unmeasured | **Re-opened for this reset, moderate.** Reset 2's timing argument against an immediate dip does not apply here |

So resets 3 and 4 look different. Reset 3 went silent for ≥ 9.4 s and then reset; reset 4 reset
within ~0.3–2.3 s while it was still running. Either they are two modes, or a single mechanism
that resets a live board (the watchdog on a stalled PID1, or supply) also covers reset 3. The
second reading needs reset 3's userspace to stall wholesale and khungtaskd's due report to miss
(~5 % base rate). This is **open**, and is the owner's call to weigh.

**What would decide between the two survivors without touching /boot.**
- **My lean:** add `watchdog0/timeleft` and PID1's state to the heartbeat, one read each per
  second.
  - **`/sys/class/watchdog/watchdog0/timeleft`** is a hardware register read (`bcm2835_wdt.c`
    `readl_relaxed(PM_WDOG)`, 1 s resolution), and it reads 11 on this boot.
  - **PID1's state** is `/proc/1/stat` field 3, and `/proc/1/wchan` if present. That is
    unverified on this image.
  - If `timeleft` counts down to 0 over the last ~14 s with PID1 in `D`, the watchdog-on-live-PID1
    case is confirmed. If it is still ~7–14 at the last line, the reset was not the watchdog, and
    supply comes forward.
  - Both reads are read-only, with no lifeline or /boot exposure. Adding them is the owner's
    decision; I have not done it.
- The fast external 5 V logger from reset 3 §4 still decides the supply question directly.

## 5. Read-only feasibility of runtime-only levers (nothing changed)

**debugfs.**
- Mounted: `debugfs /sys/kernel/debug debugfs rw,nosuid,nodev,noexec,relatime`. systemd mounts it
  at boot ("Mounted Kernel Debug File System" at [8.09] in boot −1). It is root-only (`drwx------`),
  and the ssh user is root.
- There is no `/proc/config.gz`.

**Which mmc is which** (sysfs, verified):

| host | device | driver | card |
|---|---|---|---|
| **mmc0** | `soc/20202000.mmc` | `sdhost-bcm2835` | `mmc0:5048`, type SD, "DDINC" 28.9 GiB SDHC, i.e. **the SD card (rootfs)** |
| **mmc1** | `soc/20300000.mmcnr` | `mmc-bcm2835` | `mmc1:0001`, type SDIO, with functions `mmc1:0001:1/2` under `wlan0`'s device, i.e. **the WiFi (brcmfmac): the lifeline** |

**mmc clocks**, from debugfs, read only:
- `/sys/kernel/debug/mmc0/clock`: present, `-rw-------` root, value **50000000**. `ios` shows
  actual clock 50 MHz, sd high-speed timing, 4-bit, 3.3 V.
- `/sys/kernel/debug/mmc1/clock`: present, `-rw-------` root, value **50000000**. `ios` shows
  actual 50 MHz, sd high-speed, 4-bit, 3.3 V. That is the brcmfmac SDIO clock.
- DT `brcm,overclock-50 = 0` on both, so neither is overclocked. `brcm,pio-limit=1` on sdhost.
- **Writability, from source; not exercised.** `mmc_clock_opt_set` (`core/debugfs.c`) accepts 0
  or `f_min ≤ val ≤ f_max`, claims the host, then calls `mmc_set_clock` → `set_ios`. Both host
  drivers compute a divider for any lower rate (`bcm2835_sdhost_set_clock`,
  `bcm2835_mmc_set_clock`).
- **Revert.** The change reverts at reboot. A core re-init or power-cycle of the card, for example
  in error recovery, would also restore 50 MHz silently, so a heartbeat field for `mmc0/clock`
  would be needed to prove it held.
- **Class.**
  - mmc0 is recoverable over the wire, but it is the rootfs bus. A clock that upsets the card
    stalls rootfs I/O; the likely outcome is a watchdog reset back to defaults, and otherwise a
    smart-plug cycle.
  - **mmc1 is the lifeline.** If SDIO breaks, ssh dies while the system stays up, so the watchdog
    never fires. Recovery would then be a power cycle. I would treat an mmc1 write as hands-on
    class unless it is guarded by an in-board deadman that restores 50000000. That deadman would
    itself be untested machinery.

**cpufreq.**
- `scaling_driver=cpufreq-dt`.
- OPP table, `scaling_available_frequencies` = **700000 800000 900000 1000000**. `cpuinfo` is
  700000–1000000.
- `scaling_min_freq=700000`, `scaling_max_freq=900000` (set by `kiosk-cpufreq-cap.service`,
  active and enabled), `cpuinfo_cur_freq=900000`.
- Governors: `conservative ondemand userspace powersave performance`.
- **700000 can be pinned at runtime** without changing these values. Any of `powersave` (it sits
  at `scaling_min_freq`=700000), `userspace` plus `scaling_setspeed=700000`, or `performance`
  with `scaling_max_freq=700000` would do it, and all three files are `-rw-r--r--` root. Not
  exercised. It reverts at reboot.
- Aside: this boot's `time_in_state` shows **17.42 s at 1000000 kHz**, before the cap service
  ran. Every boot spends its first seconds at the uncapped 1 GHz that raspberrypi/linux#2555
  implicates. That is outside the install window, so it is not a factor here.

**WiFi.**
- `iw` is present (`/usr/sbin/iw`). `iw dev wlan0 get power_save` gives **`Power save: on`**, and
  brcmfmac logged `brcmf_cfg80211_set_power_mgmt: power save enabled` on both boot −1 ([22.3]) and
  this boot ([21.6]).
- `wlan0` is managed, on channel 2 (2417 MHz), 20 MHz wide, txpower 31 dBm.
- Exposed brcmfmac module parameters are only `alternative_fw_path`, `debug=0` and `roamoff=1`;
  no SDIO clock parameter is exposed. The SDIO clock is mmc1's 50 MHz above.
- Toggling power save is runtime and reverts at reboot, but it touches the lifeline interface.
  `off` raises radio current draw, which is a confound if supply margin is the cause.

**Block queue, read for context.** `mmcblk0` uses `mq-deadline`, with `nr_requests` 128. The
~2.3 s read latency suggests the deadline scheduler's `read_expire` (500 ms by default; the value
was not read) is not what bounds latency here. The card-side write queue probably dominates. That
is inference.

## Classes and revert

- **Board changes: none, so there is nothing to revert.** Both sessions ran only these
  commands: `date`, `cat`/`ls`/`readlink`/`hexdump` of /proc, /sys, debugfs and device-tree
  files; `dmesg`, `journalctl`, `ps`, `rauc status`, `fw_printenv`, `systemctl show/is-active/is-enabled`,
  `timedatectl show`, `iw … get/info`.
- I deliberately read no debugfs file with bus side effects (`ext_csd` and the like). pstore was
  not mounted, so the kernel's copy of boot −1's record is no longer pending: `loop4.sh` mounted
  it read-only, copied it and unmounted it, and nothing was deleted.
- Host-side I wrote only `scratchpad/reset4/*` and this file.

## Measurement notes

- **Board sessions:** 2, each once. RSTS was read once (n = 1 this reset; n = 3 across resets, all
  0x20).
- **Healthy comparison:** batch-4 runs 1–24 (same sha, board, loop and diagnostics). They are
  compared with run 25, not pooled with it.
- **F:** 7.32–7.43 s over 14 batch-2 samples, plus 7.385 s from boot −2 to −1 today. All are
  warm reboots, there is no cold-boot sample, and the shutdown tail inside them is unmeasured.
- **Verified in source (6.12.93 work-shared tree):**
  - `scaling_cur_freq` is `policy->cur`;
  - khungtaskd skips `TASK_KILLABLE`, and page-fault and dirty-throttle waits are killable;
  - the debugfs mmc clock set path and its bounds;
  - `bcm2835_wdt` `timeleft` is a register read.
- **Not verified:**
  - that the VideoCore firmware can write PM_RSTC;
  - `/proc/1/wchan` on this image;
  - mq-deadline's tunables on this board;
  - that printk reaches the ramoops console synchronously (as in reset 3).
