# Reset 2 analysis — batch-2 loop run 14 (#245 mid-install hard reset)

Bench board only. Read-only: nothing was changed in any repo or on the board. Every board read was
an ssh with the `tools/kiosk-install.sh` options, run from a script under the bench lock
(`flock -o -w 600 ~/wisekiosk-bench/records/lock <script>`). Addresses and the hostname are written
as `<addr>` / `<host>` below.

- Record: `records/20261031T005625Z` (sha `b33eec2b6acc`). Loop summary line:
  `2026-10-30T21:05:20-0400 run=14 sha=b33eec2b6acc0a82e168064489dedaa261e857e2 exit=2 record=records/20261031T005625Z reset=yes`
- Scripts and raw outputs, committed beside this file: `reset2_window.py` (final-window
  reduction, this run and the 13 healthy batch-2 runs; its output is `reset2-window.out`),
  `board-read.sh`, `board-read2.sh`, `board-read3.sh` and their `.out` files.
- All timestamps are **host** timestamps (`-0400`) unless marked *device*.

## Verdict

**The board froze and was reset about 11 s later, while it still had power. That fits the 14 s
hardware watchdog. It does not fit a power dip that resets the board at once.** The deciding
number did not come from the capture. It came from the reboot time:

- The last sign of life was a `[stats]` line at **21:00:22.139**. The board stopped answering ssh
  keepalives by about 21:00:23.0 (worked out in §1).
- The new kernel started at **21:00:41.11**. That is **18.1–19.0 s** after the freeze.
- On this board a clean reboot goes from "Journal stopped" to kernel start in **7.32–7.43 s**
  (14 of 14 reboots in batch 2, §4). That leaves **at least 10.7 s** in which the board had power,
  did not respond, and had not yet reset.

A watchdog reset lands 7–14 s after a freeze (systemd pets every 7 s, and the timeout is 14 s), and
10.7 s falls in that window. A power dip resets the board straight away, so its kernel would start
about 7.4 s after the freeze, at about 21:00:30. It started 11 s later than that.

Strength, cause by cause:
- **Power dip with an immediate reset: ruled out, strongly.** One caveat: the 7.4 s figure was
  measured on warm reboots, not on a cold power-on.
- **Kernel panic: unlikely, moderate.** pstore was empty at boot, the timing is a little late for
  `panic=10`, and nothing reached the console.
- **Freeze, then the hardware watchdog: best supported, moderate to strong.** The reset delay fits.
  No register confirms it, because `bootstatus` carries no information on this driver (§4).

The brief's own test from the capture (does `[stats]` stop before the sessions drop?) gives a
result **neither model predicted**. `[stats]` kept a steady ~1.1 s cadence to the end, and the
sessions dropped 6.8 s and 7.8 s after the last line. So the board stopped answering ssh **at the
same moment** the stats loop stopped, not later. This is not a hang where userspace is blocked but
the network keeps answering. Everything stopped at once, and then nothing reset the board for
about 11 s.

## 1. Timeline (host clock)

Markers and stream ends, quoted:

    2026-10-30T20:58:03.208068-0400 capture started
    2026-10-30T20:58:05.745201-0400 [stats] MemFree:31328 Dirty:380 Writeback:0 load=2.37 1.58 0.75 mmc=3744 506 347438 30733 762 480 260826 120742 0 9690 151476 0 0 0 0 0 0 uv=0   (first [stats] sample)
    2026-10-30T20:58:06.131744-0400 [kernel] 2026-10-30T20:58:06,117058-04:00 audit: type=1302 audit(1793408286.089:34): item=6 name=(null) inode=7707 dev=00:08 mode=040755 ouid=0 ogid=0 rdev=00:00 nametype=PARENT cap_fp=0 cap_fi=0 cap_fe=0 cap_fver=0 cap_frootid=0   (LAST real [kernel] line)
    2026-10-30T20:58:07.223453-0400 [journal] 2026-10-30T20:58:06.520389-04:00 <host> rauc[299]: writing data to device /dev/mmcblk0p2   (LAST real [journal] line)
    2026-10-30T21:00:22.139476-0400 [stats] MemFree:47176 Dirty:9720 Writeback:35308 load=4.31 2.59 1.24 mmc=4866 517 618726 81803 3662 372190 3190564 4574054 0 112140 4655858 0 0 0 0 0 0 uv=0   (LAST [stats] line)
    2026-10-30T21:00:28.956962-0400 [journal] Timeout, server <addr> not responding.
    2026-10-30T21:00:28.957545-0400 [journal] session ended
    2026-10-30T21:00:29.960487-0400 [kernel] Timeout, server <addr> not responding.
    2026-10-30T21:00:29.960487-0400 [stats] Timeout, server <addr> not responding.
    2026-10-30T21:00:29.960993-0400 [stats] session ended
    2026-10-30T21:00:29.961085-0400 [kernel] session ended
    Read from remote host <addr>: Connection reset by peer        (stderr, unstamped: the rauc-install ssh)
    client_loop: send disconnect: Broken pipe                    (stderr, unstamped)
    2026-10-30T21:05:20.313445-0400 capture stopped
    error: recipe `kiosk-install` failed on line 235 with exit code 255

The last rauc progress line printed was ` 84% Copying image to rootfs.0`. The `[kernel]` and
`[journal]` streams fell silent 2 min 15 s before the drop. That silence is normal for the copy
phase: the same 60 s window holds 0 `[kernel]` and 0 `[journal]` lines in three healthy batch-2
runs (`20261031T002723Z`, `…003728Z`, `…004645Z`).

**Gaps from the last `[stats]` line (21:00:22.139476):**

| event | at | gap |
|---|---|---|
| `[journal] session ended` | 21:00:28.957545 | **6.818 s** |
| `[stats] session ended` | 21:00:29.960993 | **7.822 s** |
| `[kernel] session ended` | 21:00:29.961085 | **7.822 s** |
| `capture stopped` | 21:05:20.313445 | 298.17 s |

**Cadence of the last `[stats]` lines:** steady right to the end. There was no early stop and no
burst. The final eight gaps were 1.115, 1.145, 1.121, 1.227, 1.126, 1.252, 1.035 and 1.132 s, and
every gap in the final 60 s fell in 1.02–1.27 s. The 13 healthy batch-2 runs show 0.86–2.48 s over
the same window. The one long gap in this run (4.59 s, 20:58:09.51 → 20:58:14.11) is at copy start,
like the healthy runs, and inside the baseline's 1.5–7.7 s range.

**What the keepalive timing pins down.** The host runs OpenSSH 10.2. My model of its client loop
comes from memory, not from re-reading the source; the constant 1.00 s split between sessions in
both resets fits it. In that model each session sends a keepalive on a fixed 2 s schedule. Any packet received resets the miss counter, and the session exits on the
4th check with no reply (ServerAliveInterval 2, CountMax 3). So an exit at time *X* means a packet
arrived after *X*−8 s and nothing arrived after *X*−6 s.
- `[stats]` exited at 29.960. The line at 22.139 was received, and the keepalive sent at about
  23.96 got no answer. The next stats sample, due about 23.27, never arrived.
- `[journal]` exited at 28.957. The keepalive sent at about 20.96 was answered, and the one sent at
  about **22.96 was not**.
- Together: the board stopped answering ssh between **22.14 and about 23.0**, within about 0.9 s of
  its last stats sample and before the next one was due. The two sessions ending 1.00 s apart, both
  here and in run 1, is only the two sessions' 2 s schedules being out of phase.

The rauc-install ssh has no ServerAlive. It ended only when a retransmission reached the rebooted
kernel and drew a RST, at about 21:05:20 (about 298 s of TCP backoff). That time does not mark when
the board came back.

## 2. Final 60 s against the healthy ranges

There are 53 samples, 20:59:22.27 → 21:00:22.14. Field 7 of `mmc=` is sectors written, 512 B each.
Field 9 is in-flight I/O.

| metric | run 14, final 60 s | 13 healthy batch-2 runs, same elapsed window (138.9 s after capture start; per run) | batch-1 whole-run baseline (33 runs) |
|---|---|---|---|
| MemFree (kB) | 43 640 .. 74 896 | min per run 10 784 .. 74 200 | min per run 10 384 .. 35 508 |
| Dirty max (kB) | 47 028 | 44 820 .. 49 612 | 32 552 .. 55 568 |
| Writeback max (kB) | 44 012 | 40 448 .. 48 488 | 42 368 .. 51 640 |
| load1 max | 4.31 (rising 3.40 → 4.31) | 4.39 .. 5.98 | 4.99 .. 6.50 |
| SD write MB/s min / mean / max | 7.47 / 14.59 / 17.30 | min 0.00–8.44, mean 12.25–14.36, max 17.87–21.23 | peak 18.79 .. 23.72 |
| longest zero-write interval | 0 s | 0 .. 2.5 s | 2.5 .. 4.1 s (whole run) |
| in-flight I/O (field 9) | 0 in every sample | 0 in every sample of every run | — |
| uv | 0 in every sample | 0 | never 1 in any run |

**Nothing is outside the healthy range in a way that means anything.**
- Writes kept going to the last sample: the final interval wrote 37 888 sectors in 1.132 s
  (17.14 MB/s), with io_ticks +1040 ms. The card was taking writes at full rate until the end.
  There was no slowdown, no stall and no queue build-up.
- The only edges: mean write rate 14.59 MB/s is 0.23 MB/s above the highest healthy mean (n=13),
  and peak load 4.31 is 0.08 below the lowest healthy peak. Both are small next to the spread
  between runs, so I read them as noise.
- Field 9 reads 0 in every sample of every run, so it cannot show anything here.
- Over the whole window, run 14's figures sit inside the 33-run baseline: min MemFree 12 016, max
  Dirty 48 364, max Writeback 44 012, max `[stats]` gap 4.59 s. It wrote 1 500 MB before it died.


Every `[stats]` line in the final 60 s (verbatim):

    2026-10-30T20:59:22.267815-0400 [stats] MemFree:47944 Dirty:5376 Writeback:39936 load=3.40 2.09 1.00 mmc=4858 517 618606 74599 1988 161697 1482004 1619528 0 58540 1694128 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:23.358845-0400 [stats] MemFree:47944 Dirty:5376 Writeback:22016 load=3.53 2.13 1.02 mmc=4858 517 618606 74599 2024 161697 1518868 1713990 0 59820 1788590 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:24.433625-0400 [stats] MemFree:47944 Dirty:5376 Writeback:7168 load=3.53 2.13 1.02 mmc=4858 517 618606 74599 2053 161697 1548564 1787961 0 60920 1862561 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:25.628222-0400 [stats] MemFree:45712 Dirty:29664 Writeback:1028 load=3.53 2.13 1.02 mmc=4859 517 618614 77341 2072 162459 1565996 1829605 0 61420 1906946 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:26.818670-0400 [stats] MemFree:49816 Dirty:45152 Writeback:1028 load=3.53 2.13 1.02 mmc=4859 517 618614 77341 2101 166142 1595692 1833226 0 62590 1910567 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:28.040003-0400 [stats] MemFree:66540 Dirty:45568 Writeback:1028 load=3.73 2.20 1.04 mmc=4859 517 618614 77341 2134 170333 1629484 1836281 0 63560 1913623 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:29.181638-0400 [stats] MemFree:66752 Dirty:44936 Writeback:776 load=3.73 2.20 1.04 mmc=4859 517 618614 77341 2171 175032 1667372 1840401 0 64860 1917743 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:30.305387-0400 [stats] MemFree:74896 Dirty:36044 Writeback:11784 load=3.73 2.20 1.04 mmc=4859 517 618614 77341 2197 180874 1693996 1844689 0 65860 1922031 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:31.407538-0400 [stats] MemFree:74452 Dirty:45708 Writeback:1028 load=3.73 2.20 1.04 mmc=4859 517 618614 77341 2232 182531 1727852 1861983 0 66780 1939325 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:32.520405-0400 [stats] MemFree:64036 Dirty:4556 Writeback:42072 load=3.73 2.20 1.04 mmc=4860 517 618622 77393 2262 196395 1758572 1871571 0 67810 1948964 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:33.680133-0400 [stats] MemFree:51716 Dirty:12176 Writeback:33880 load=3.75 2.23 1.06 mmc=4860 517 618622 77393 2295 199012 1792364 1911886 0 68870 1989280 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:34.819845-0400 [stats] MemFree:47260 Dirty:6092 Writeback:40536 load=3.75 2.23 1.06 mmc=4860 517 618622 77393 2328 204523 1826156 1984975 0 69790 2062369 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:35.951159-0400 [stats] MemFree:48312 Dirty:6692 Writeback:39000 load=3.75 2.23 1.06 mmc=4860 517 618622 77393 2364 208587 1863020 2082950 0 70930 2160343 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:37.180012-0400 [stats] MemFree:44536 Dirty:6668 Writeback:39000 load=3.75 2.23 1.06 mmc=4860 517 618622 77393 2398 214186 1897836 2168342 0 72010 2245735 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:38.297091-0400 [stats] MemFree:48140 Dirty:9468 Writeback:39000 load=3.93 2.29 1.09 mmc=4860 517 618622 77393 2428 216715 1928556 2245890 0 73060 2323283 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:39.426342-0400 [stats] MemFree:46188 Dirty:8092 Writeback:36952 load=3.93 2.29 1.09 mmc=4860 517 618622 77393 2464 220779 1965420 2340497 0 74100 2417890 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:40.548284-0400 [stats] MemFree:46880 Dirty:8592 Writeback:36440 load=3.93 2.29 1.09 mmc=4860 517 618622 77393 2497 224843 1999212 2432209 0 75130 2509602 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:41.667178-0400 [stats] MemFree:46196 Dirty:8940 Writeback:36440 load=3.93 2.29 1.09 mmc=4861 517 618638 77696 2529 228907 2031980 2515423 0 76110 2593119 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:42.862682-0400 [stats] MemFree:46432 Dirty:11200 Writeback:34392 load=3.94 2.32 1.10 mmc=4861 517 618638 77696 2566 232971 2069868 2608668 0 77190 2686365 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:43.995681-0400 [stats] MemFree:44800 Dirty:11816 Writeback:35416 load=3.94 2.32 1.10 mmc=4861 517 618638 77696 2596 237035 2100588 2686669 0 78240 2764365 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:45.114737-0400 [stats] MemFree:47164 Dirty:10976 Writeback:34904 load=3.94 2.32 1.10 mmc=4861 517 618638 77696 2628 241099 2133356 2773243 0 79240 2850940 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:46.294984-0400 [stats] MemFree:46516 Dirty:12548 Writeback:36400 load=3.94 2.32 1.10 mmc=4861 517 618638 77696 2664 247195 2170220 2870378 0 80290 2948075 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:47.529776-0400 [stats] MemFree:45356 Dirty:4588 Writeback:40536 load=3.94 2.32 1.10 mmc=4861 517 618638 77696 2698 251259 2205036 2958490 0 81390 3036187 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:48.658958-0400 [stats] MemFree:45248 Dirty:5356 Writeback:40024 load=3.94 2.35 1.12 mmc=4861 517 618638 77696 2730 255323 2237804 3041745 0 82430 3119442 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:49.732948-0400 [stats] MemFree:48048 Dirty:11916 Writeback:31832 load=3.94 2.35 1.12 mmc=4861 517 618638 77696 2761 257355 2269548 3122644 0 83440 3200341 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:50.971071-0400 [stats] MemFree:48048 Dirty:11916 Writeback:13400 load=3.94 2.35 1.12 mmc=4861 517 618638 77696 2797 257355 2306412 3218010 0 84550 3295706 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:51.991170-0400 [stats] MemFree:51216 Dirty:17148 Writeback:0 load=3.94 2.35 1.12 mmc=4863 517 618678 79878 2824 257355 2333212 3285384 0 85420 3365263 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:53.171497-0400 [stats] MemFree:45172 Dirty:42152 Writeback:1028 load=3.87 2.36 1.13 mmc=4863 517 618678 79878 2850 260911 2359836 3287812 0 86230 3367691 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:54.322982-0400 [stats] MemFree:46632 Dirty:45084 Writeback:1028 load=3.87 2.36 1.13 mmc=4863 517 618678 79878 2882 264975 2392604 3291291 0 87320 3371169 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:55.449409-0400 [stats] MemFree:49352 Dirty:46296 Writeback:1028 load=3.87 2.36 1.13 mmc=4863 517 618678 79878 2914 269039 2425372 3294649 0 88400 3374528 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:56.589330-0400 [stats] MemFree:47988 Dirty:45084 Writeback:1028 load=3.87 2.36 1.13 mmc=4863 517 618678 79878 2948 273357 2460188 3298016 0 89410 3377895 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:57.811260-0400 [stats] MemFree:48736 Dirty:2352 Writeback:43140 load=4.12 2.44 1.16 mmc=4864 517 618686 79924 2980 287613 2492956 3308683 0 90330 3388608 0 0 0 0 0 0 uv=0
    2026-10-30T20:59:59.080314-0400 [stats] MemFree:47512 Dirty:11536 Writeback:34948 load=4.12 2.44 1.16 mmc=4864 517 618686 79924 3013 291610 2526748 3355069 0 91410 3434994 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:00.150750-0400 [stats] MemFree:48404 Dirty:5640 Writeback:23684 load=4.12 2.44 1.16 mmc=4864 517 618686 79924 3048 291677 2562588 3446359 0 92450 3526284 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:01.375906-0400 [stats] MemFree:69220 Dirty:10640 Writeback:7300 load=4.12 2.44 1.16 mmc=4865 517 618694 81757 3082 291677 2597404 3540049 0 93660 3621807 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:02.541599-0400 [stats] MemFree:45764 Dirty:38372 Writeback:1028 load=4.12 2.44 1.16 mmc=4865 517 618694 81757 3109 293709 2624292 3575282 0 94610 3657040 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:03.675343-0400 [stats] MemFree:46768 Dirty:45308 Writeback:1028 load=4.03 2.45 1.17 mmc=4865 517 618694 81757 3145 298281 2661156 3578423 0 95630 3660181 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:04.860006-0400 [stats] MemFree:44040 Dirty:44804 Writeback:1028 load=4.03 2.45 1.17 mmc=4865 517 618694 81757 3177 302345 2693924 3582099 0 96790 3663856 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:06.003044-0400 [stats] MemFree:50184 Dirty:47028 Writeback:1028 load=4.03 2.45 1.17 mmc=4865 517 618694 81757 3206 306028 2723620 3585712 0 97940 3667470 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:07.237912-0400 [stats] MemFree:49300 Dirty:46636 Writeback:1028 load=4.03 2.45 1.17 mmc=4865 517 618694 81757 3241 310473 2759460 3588651 0 98840 3670408 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:08.441626-0400 [stats] MemFree:45016 Dirty:22792 Writeback:28592 load=4.27 2.52 1.20 mmc=4866 517 618726 81803 3277 322556 2796324 3593468 0 100100 3675272 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:09.560900-0400 [stats] MemFree:44152 Dirty:6488 Writeback:40448 load=4.27 2.52 1.20 mmc=4866 517 618726 81803 3306 328253 2826020 3619126 0 101140 3700930 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:10.679898-0400 [stats] MemFree:47116 Dirty:8060 Writeback:39936 load=4.27 2.52 1.20 mmc=4866 517 618726 81803 3337 332317 2857764 3676718 0 101890 3758521 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:11.815267-0400 [stats] MemFree:48136 Dirty:6684 Writeback:38400 load=4.27 2.52 1.20 mmc=4866 517 618726 81803 3374 336381 2895652 3779317 0 103190 3861121 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:12.985371-0400 [stats] MemFree:49584 Dirty:6112 Writeback:41472 load=4.25 2.55 1.22 mmc=4866 517 618726 81803 3400 340445 2922276 3849441 0 104270 3931245 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:14.100657-0400 [stats] MemFree:43640 Dirty:8844 Writeback:38508 load=4.25 2.55 1.22 mmc=4866 517 618726 81803 3433 344154 2956068 3939349 0 105130 4021153 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:15.246126-0400 [stats] MemFree:47740 Dirty:7200 Writeback:37996 load=4.25 2.55 1.22 mmc=4866 517 618726 81803 3467 348218 2990884 4034605 0 106350 4116409 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:16.367377-0400 [stats] MemFree:49708 Dirty:8236 Writeback:39532 load=4.25 2.55 1.22 mmc=4866 517 618726 81803 3496 352282 3020580 4112774 0 107420 4194578 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:17.594285-0400 [stats] MemFree:49180 Dirty:9156 Writeback:38508 load=4.25 2.55 1.22 mmc=4866 517 618726 81803 3529 356346 3054372 4203336 0 108290 4285140 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:18.720305-0400 [stats] MemFree:48352 Dirty:1636 Writeback:44012 load=4.31 2.59 1.24 mmc=4866 517 618726 81803 3564 362030 3090212 4300637 0 109490 4382441 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:19.972609-0400 [stats] MemFree:45204 Dirty:9524 Writeback:37356 load=4.31 2.59 1.24 mmc=4866 517 618726 81803 3593 364062 3119908 4380530 0 110300 4462334 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:21.007910-0400 [stats] MemFree:47936 Dirty:10828 Writeback:36844 load=4.31 2.59 1.24 mmc=4866 517 618726 81803 3625 368126 3152676 4468324 0 111100 4550127 0 0 0 0 0 0 uv=0
    2026-10-30T21:00:22.139476-0400 [stats] MemFree:47176 Dirty:9720 Writeback:35308 load=4.31 2.59 1.24 mmc=4866 517 618726 81803 3662 372190 3190564 4574054 0 112140 4655858 0 0 0 0 0 0 uv=0

## 3. Non-boilerplate `[kernel]`/`[journal]` lines in the final 60 s

**None.** From 20:59:22 to the drop, the only `[kernel]` and `[journal]` lines are the two ssh
`Timeout, server <addr> not responding.` lines quoted in §1. The last real kernel line was at
20:58:06.13 and the last real journal line at 20:58:07.22 (`writing data to device`). After that
there was nothing: no mmc error, no lockup or hung-task message, no under-voltage line, no oops.
Healthy runs are just as silent in this window (§1), so the silence tells us nothing. The persistent
journal on the board matches: boot −1 ends on the same rauc line (§4).

## 4. Board state after the reset (read 21:08–21:13, read-only)

- **Uptime and boot time.** The board read `478.23 339.27` from `/proc/uptime` at host epoch
  1793408918.4–925.5. The current kernel log, with the clock now NTP-synced, gives *device*
  `2026-10-30T21:00:41,113826-04:00 Booting Linux on physical CPU 0x0`.
  - Cross-check: I sampled three device-clock second edges with host stamps. Device epoch
    1793409047 coincided with uptime 605.91 and was received on the host at 1793409047.038. So the
    device clock is within about 0.1 s of the host, and kernel start = **21:00:41.09–41.14 host**.
  - In the same boot: `bcm2835-wdt … Broadcom BCM2835 watchdog timer` at 21:00:44.06, and
    `systemd[1]: Watchdog running with a hardware timeout of 14s.` at 21:00:45.76.
  - NTP's first sync was `Initial clock synchronization to Fri 2026-10-30 21:01:40.488594 EDT.`.
    Boot 0's earliest journal stamps (20:59:15) come from before that sync and read about 1.5 min early.
    Do not use them for timing.
- **`journalctl --list-boots`** (tail):

      -2 733d7fd44b1f49cbacbe4736358b9fea Fri 2026-10-30 20:42:44 EDT Fri 2026-10-30 20:52:04 EDT
      -1 8586ebf489a84109b661633bbd49f3cf Fri 2026-10-30 20:52:05 EDT Fri 2026-10-30 20:58:06 EDT
       0 ed18d67a158e4820852426b87cff5433 Fri 2026-10-30 20:59:15 EDT Fri 2026-10-30 21:08:39 EDT

  Boot 0's first journald entry: `File …/system.journal corrupted or uncleanly shut down, renaming
  and replacing.`
- **Tail of boot −1** (`journalctl -b -1 -o short-iso-precise | tail -40`). The final lines:

      2026-10-30T20:58:06.169105-04:00 <host> rauc[299]: Marking target slot rootfs.0 as non-bootable (bad)...
      2026-10-30T20:58:06.375638-04:00 <host> rauc[299]: Marked slot rootfs.0 as bad
      2026-10-30T20:58:06.414709-04:00 <host> rauc[299]: installing /data/update.raucb: Updating slots...
      2026-10-30T20:58:06.414816-04:00 <host> rauc[299]: installing /data/update.raucb: Checking slot rootfs.0
      2026-10-30T20:58:06.515131-04:00 <host> rauc[299]: Updating slot rootfs.0
      2026-10-30T20:58:06.515248-04:00 <host> rauc[299]: Updating /dev/mmcblk0p2 with /run/rauc/mnt/bundle/core-image-base-raspberrypi0-wifi.rootfs.ext4
      2026-10-30T20:58:06.518703-04:00 <host> rauc[299]: installing /data/update.raucb: Updating slot rootfs.0
      2026-10-30T20:58:06.519607-04:00 <host> rauc[299]: opening slot device /dev/mmcblk0p2
      2026-10-30T20:58:06.520389-04:00 <host> rauc[299]: writing data to device /dev/mmcblk0p2

  The 31 lines before these are the bundle mount, the dm-verity setup and its `audit` lines, all
  stamped 20:58:06.0–06.15. Nothing on disk is later than 20:58:06.52, so the last 2 min 16 s of
  journal never reached the card.
- **`/sys/fs/pstore`:** empty, holding only `.` and `..`.
  - `systemd-pstore.service` shows `ConditionResult=no`, so its not-empty condition failed at boot.
  - `/var/lib/systemd/pstore` does not exist. Nothing was archived and removed; the store really
    was empty at boot.
- **`/sys/class/watchdog/watchdog0`:**
  - Values: `bootstatus=0`, `timeout=14`, `timeleft=13`, `state=active`, `status=0x8000`,
    `nowayout=0`.
  - **`bootstatus` carries no information on this board.** The board runs 6.12.93, and I read the
    6.12.93 source in `build/…/work-shared/raspberrypi0-wifi/kernel-source`. Its
    `drivers/watchdog/bcm2835_wdt.c` never assigns `bootstatus`. It writes `PM_RSTS` only to pass
    the reboot partition. So `0` reads the same after a watchdog reset and after a power-on.
- **uv now:** `/sys/class/hwmon/hwmon1 rpi_volt 0`.
- **`rauc status`:** booted `rootfs.1 (B)`, activated `rootfs.1 (B)`. Slot B `good`, slot A
  (`/dev/mmcblk0p2`) `bad`. `fw_printenv`: `BOOT_ORDER=B`, `BOOT_A_LEFT=0`, `BOOT_B_LEFT=3`. The
  board fell back to the last-good slot as designed, and the half-written A is marked bad.

**Reference measurement: warm reboot to kernel start on this board.** Each boot's "Journal stopped"
(*device* clock, synced, skew 0 s measured at install time) is paired with the next boot's
`Booting Linux` stamp (from each run's `[kernel]` backlog, rendered while synced). n = 14, all of
batch 2:

| boot ended (Journal stopped) | next kernel start | Δ (s) |
|---|---|---|
| 18:23:13.558 | 18:23:20.932 | 7.374 |
| 18:57:23.000 | 18:57:30.418 | 7.418 |
| 19:06:58.113 | 19:07:05.505 | 7.392 |
| 19:16:32.931 | 19:16:40.303 | 7.372 |
| 19:25:52.738 | 19:26:00.096 | 7.358 |
| 19:36:14.460 | 19:36:21.817 | 7.357 |
| 19:45:22.040 | 19:45:29.418 | 7.378 |
| 19:54:20.656 | 19:54:28.090 | 7.434 |
| 20:04:12.033 | 20:04:19.353 | 7.320 |
| 20:13:55.117 | 20:14:02.493 | 7.376 |
| 20:23:27.382 | 20:23:34.718 | 7.336 |
| 20:32:55.885 | 20:33:03.278 | 7.393 |
| 20:42:43.247 | 20:42:50.616 | 7.369 |
| 20:52:04.291 | 20:52:11.668 | 7.377 |

Range **7.32–7.43 s**. This includes the systemd-shutdown tail after journald stops, so the
firmware and u-boot time from reset to kernel start, F, is **at most 7.43 s**. For a warm reset, a
`reboot` and a watchdog timeout are the same PM_RSTC full-reset path on this SoC.

**This reset:** from the freeze (22.14–23.0) to kernel start (41.11) is **18.1–19.0 s**.
Subtracting F (at most 7.43 s) leaves **R ≥ 10.7 s** between the freeze and the reset. R is about
10.7–11.7 s if the shutdown tail is near zero, and up to about 14 s if the tail were about 2–3 s.

## 5. Which cause?

| hypothesis | predicts | observed | verdict |
|---|---|---|---|
| **Power dip** (the board dies when the rail drops and resets as it recovers) | `[stats]` regular to the end ✓. Sessions end about 6–8 s after the last line ✓. **Kernel starts about F (≤ 7.4 s) after death, by about 21:00:30.4.** pstore empty ✓. | Kernel started at 21:00:41.1, **at least 10.7 s later than an immediate reset allows** | **Ruled out for a dip that resets at once. Strong:** 14 warm-boot samples spread 0.11 s, against a 10.7 s excess. Still open: an outage lasting about 11 s, or a cold boot that takes about 11 s longer than a warm one. Neither was measured. |
| **Hang, then hardware watchdog** | The board is powered but unresponsive, and the reset comes 7–14 s after the freeze (14 s timeout, pets every 7 s). pstore empty ✓. | R is about 10.7 s, and up to about 14 s | **Best supported. Moderate to strong.** The reset delay falls inside the watchdog window, and nothing else on the board resets after a delay like that. It cannot be confirmed from a register (`bootstatus` carries no information). |
| ↳ the brief's form: userspace blocked, network alive | `[stats]` stops first; sessions keep answering and drop only after the reset | Sessions stopped answering within about 0.9 s of the last sample, about 11 s **before** the reset | **This form is ruled out.** The hang stopped everything that answers ssh at once. Either the kernel or CPU froze, or the I/O wedged so hard that sshd blocked too (its pages could have been evicted by the 1.5 GB write; that is not measured). |
| **Kernel panic** (`panic=10`) | A dmesg-zone record in pstore. Reset about 10 s plus print time after the panic, so kernel start about 17.4–18 s after death. | pstore empty and `systemd-pstore` condition false. Kernel start 18.1–19.0 s after the last sign of life. | **Disfavored. Moderate.** The main evidence is the empty pstore. The August wifi investigation captured oopses in kmsg-dump format with ramoops on this board, but under kernel 6.6, and I did not re-prove it under 6.12. The timing is only marginally late (0.1–1.6 s), so it is weak evidence. |

**What the evidence cannot decide.**
1. **What froze the board.** The candidates are a CPU or kernel lockup with interrupts off, a
   wedged SD-host or SDIO bus, or a voltage sag deep enough to hang the SoC but not reset it, after
   which the watchdog did the reset. `uv` was 0 in every 1 Hz sample to 22.14, but a sag in the
   final second would fall between samples. The capture is silent at the freeze: no console line,
   no counter trend.
2. **Whether the reset was the watchdog or an outage of about 11 s.** Both leave the same empty
   pstore and the same `bootstatus=0`.
3. **Warm versus cold boot time.** F was measured on warm reboots only.

**One observable that would decide it: the SoC's own reset-cause register, `PM_RSTS`, read once at
early boot.** Its `HADWRF` (watchdog full reset) and `HADPOR` (power-on reset) bits tell a watchdog
reset from a power cycle directly. The data above can only infer that from timing. The board has no
`vcgencmd get_rsts` (BusyBox userland), and the driver does not export it as `bootstatus`, so
getting it means a raw register read or a boot-time hook. I did not try a `/dev/mem` read: a wrong
peripheral address can abort the CPU, and this task was read-only.

Two weaker substitutes, neither tried: a 1 Hz power log on the bench supply or plug, which would
show an 11 s outage; and one cold power-cycle timing (outlet off and on, then `Booting Linux`
minus the power-on moment), which would close the cold-boot caveat. For **what** froze it,
`netconsole` streaming to the host is the instrument. The module already ships, and the
instrument notes say it is not loaded. It would catch a lockup or mmc message printed while the
journal could not flush.

**Run 1 compared, not blended.** In the first reset (`run1-reset.log`), the sessions ended
00:28:11.37 / 00:28:12.37, 138.4 s after capture start. It shows the same 1 s split between the
two sessions and the same "Connection reset by peer" after about 5 min. Both deaths fall about
129–136 s into the slot copy, at the last progress lines 80% and 84%, and every one of the 46
healthy runs got past that point. With n = 2 this cannot tell "the same image offset or card
region" apart from "the same elapsed time".
