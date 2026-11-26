# Why TST008 could not apply its network load on the bench board

| | |
|---|---|
| **Issue** | #408 TST008 cannot apply its network load on the bench board |
| **Status** | open: cause narrowed to the bench's radio link; the two-board watch that splits it is pending |
| **Opened / concluded** | 2026-11-25 / — |

TST008 (`test_sustained_network_load`) pushes random 1 MiB blocks from the bench host into `ssh <board>
wc -c` for 60 s and is valid only if the board takes at least 1.0 MB/s. It passed on the bench at 01:39
EST on 25 Nov and was INVALID six times from 18:17 at 0.29-0.67 MB/s, on two kernels. The kernel, the
image, the test code, the runner, the host's sending path, the ssh cipher, the board's CPU clock, its
configuration on `/data` and the kiosk page's CPU load are each ruled out. The push rate follows the
bench's Wi-Fi receive rate: 2.1 MB/s while the AP sends to it at 19.5-58.5 MBit/s, and 0.49 MB/s while
it sends at 5.5 MBit/s, with the board's CPU half idle. Episodes at 5.5 MBit/s last over a minute. Prod,
on the same AP and channel with 24 dB more signal, held 72.2 MBit/s with no failed transmissions over
the same minutes. Still open: whether the bench's own link fails, or channel events hit both boards and
only the bench, with less margin, falls; and whether such an episode sits inside every INVALID call.

All times EST. Records named `<UTC timestamp>Z` are bench-runner records (`bench test` output), kept on
the bench host, not in this repository.

## Test runs

| Run | Board (role) | Image commit | Harness / scripts | Result (1 line) |
|---|---|---|---|---|
| 1 | bench · Pi Zero W | `a47f215` | TST008, `tests/target_suite/test_back_on_the_panel.py` — durable | record 20261125T062415Z: passed, 4.5 s off |
| 2 | bench · Pi Zero W | `e0b3363` | TST008 — durable | 20261125T225710Z: INVALID, 0.67 MB/s, 32.0 s off, 41.5 s after a power cut |
| 3 | bench · Pi Zero W | `e0b3363` | TST008 — durable | 20261126T000054Z: INVALID, 0.29 MB/s, 32.8 s off |
| 4 | bench · Pi Zero W | `afcbaa3` | TST008 + `ctl-*.sh` — one-off | 20261126T002708Z: INVALID, 0.40 MB/s, 40.9 s off (main's kernel) |
| 5 | bench · Pi Zero W | `e0b3363` | TST008 + `ctl-*.sh` — one-off | 20261126T003329Z: INVALID, 0.35 MB/s, 48.9 s off |
| 6 | bench · Pi Zero W | `e0b3363` | TST008 + `ctl-*.sh` — one-off | 20261126T003601Z: INVALID, 0.51 MB/s, 28.8 s off |
| 7 | prod · Pi Zero W | `a47f215` | TST008 — durable | prod 20261126T004619Z: passed, 3.8 s off |
| 8 | bench · Pi Zero W | `6a34d6f` | `netread.sh` and its drivers, `tst008-ss-sample.sh` — one-off | bare pushes: 0.40 MB/s (default cipher), 1.46 (aes128-ctr), 0.30 board to host |
| 9 | bench · Pi Zero W | `6a34d6f` | `tst008-cipher-aba.sh`, `a103*.sh` — one-off | default 1.77, aes128-ctr 1.67, default 2.34 MB/s |
| 10 | bench · Pi Zero W | `6a34d6f` | `tst008-rate-track.sh`, `ratetrack.sh` — one-off | 2.16, 2.08, 0.77, 0.49 MB/s; rate follows the radio rate |
| 11 | bench · Pi Zero W | `6a34d6f` | TST008 + `station-read.sh` — one-off | 20261126T015444Z: VOID (a login inside the call) |
| 12 | bench · Pi Zero W | `6a34d6f` | TST008 + `station-read.sh`, `tst008-rerun2.sh` — one-off | 20261126T020536Z: INVALID, 0.57 MB/s, 29.5 s off |
| 13 | prod · Pi Zero W | `a47f215` | `radio-watch.sh` — one-off | 102 samples: rx 72.2 MBit/s in 88, tx failed flat at 4 |
| 14 | prod · Pi Zero W | `a47f215` | `kiosk-soak` (durable) read by a one-off `awk` | the day's 5-minute load series |

Run 10 also read the bench's `kiosk-soak` log since 22 Nov; that series spans many boots and images and
is used only for its time-of-day shape.

### Runs 1-7 — TST008 as the suite runs it

- **Boards:** bench and prod, Pi Zero W. **Image commits** from each record's `board_commit` and the
  slot reads in `run-control-reads-bench.txt`.
- **Procedure:** `bench test <commit> --skip-build -- -k test_sustained_network_load` (runs 3-7), or
  the suite (runs 1-2). Runs 4-6 are a slot switch on the bench: the other slot (`afcbaa3`, main's
  kernel) booted with `rauc status mark-active` and one reboot, TST008 once, back to `e0b3363`, TST008
  twice; reads before and after each call, none inside it (`ctl-run.sh`).
- **Raw capture:** the records; `run-control-reads-bench.txt` for runs 4-6.

### Run 8 — bare pushes, with the sender's TCP state

- **Procedure** (`netread.sh 1 2 3`, then `4 5`, its arguments naming the parts below; the pull again by
  `netread3b.sh`). *Baseline:* board reads (wireless, `iw dev wlan0 link`, cpufreq, under-voltage alarm,
  temperature, `top`, journal size, `/data/config` hashes) and 20 host pings. *Push:* 30,000,000 B of
  random data from the host into `ssh <board> wc -c`, beside a board `top` (4 x 5 s), 60 host pings and
  `tst008-ss-sample.sh` (host `ss -tin` every 2.5 s). *Pull:* the reverse direction (`dd if=/dev/zero
  bs=1000000 count=30` on the board). *AES push:* the push with `-c aes128-ctr`. *Baseline again.* The
  host was quiet for the baseline and the push; the pull and the AES push ran beside a kernel compile.
  The pull's first form used `head -c`, which this image's busybox lacks: it sent nothing and is void;
  `netread.sh` holds only the rerun's form.
- **Raw capture:** `run-netread-bench.txt`.

### Run 9 — cipher A/B/A

- **Procedure:** `tst008-cipher-aba.sh` (wrapped by `a103.sh`): three 30,000,000 B pushes back to back,
  default cipher, `aes128-ctr`, default; `iw station dump` and loadavg before and after each, board
  `top` beside. Beside a kernel compile (printed). Its `ss` sections are empty: the sampler was handed
  `root@<board>` and could not parse it (fixed before run 10).
- **Raw capture:** `run-cipher-aba-bench.txt` (ends with the bench `kiosk-soak` lines for 25 Nov).

### Run 10 — push rate against the radio rate

- **Procedure:** `tst008-rate-track.sh` (wrapped by `ratetrack.sh`): four 30,000,000 B pushes, default
  cipher; beside each, one board ssh samples `iw dev wlan0 station dump` (rx and tx bitrate, tx failed)
  and `top`'s CPU line every 2 s, a known board load equal in all four; then the bench `kiosk-soak` log
  since 22 Nov. Beside a host build (printed).
- **Raw capture:** `run-rate-track-bench.txt`.

### Runs 11-12 — TST008 with the radio read outside the call

- **Procedure:** `station-read.sh` before and after the call, `tst008-rerun2.sh` for run 12. Run 11's
  "before" read landed 5 s inside the call, so run 11 is void and is not used. Run 12's before read
  ended about 5 min before the call; a before read should end within 60 s of the call's start.
- **Raw capture:** `run-station-reads-bench.txt` and the records.

### Runs 13-14 — prod's radio and load

- **Procedure:** run 13, `radio-watch.sh <prod> prod <out> 102` (one ssh, every 10 s: uptime, rx and tx
  bitrate, tx failed, signal, frequency, loadavg); the AP prod is associated with was compared with the
  bench's in shell variables only and reported as same or different. Run 14, one ssh: `wc -l`, `tail -n
  1` and an `awk` over `/data/kiosk-soak.log` for 25 Nov.
- **Raw capture:** `run-radio-watch-prod-2103.txt`, `run-soak-prod.txt`.

Run 13 used `radio-watch.sh` before its output was made line-buffered (`sed -u`); the reads are the same.
Run 8 used `tst008-ss-sample.sh` before it learned to strip a `user@` prefix from its argument; the reads are
the same.
A bench watch started beside it was killed by its process group and lost all its output to that
buffering; it is not a run here.

## Configuration under test

- The load and its floor: `tests/board/network/__init__.py` (`_LOAD_FLOOR_MB_S = 1.0`,
  `Network.load`, `Load.confirm_applied`); the call: `tests/target_suite/test_back_on_the_panel.py`
  (`test_sustained_network_load`).
- The host ssh client offers `chacha20-poly1305@openssh.com` first (`ssh -G`, OpenSSH 10.2p1); no host
  ssh package or configuration changed this month.
- The board's CPU is capped at 900 MHz:
  [`kiosk-cpufreq-cap.service`](../../../meta-wisekiosk/recipes-core/kiosk-cpufreq/files/kiosk-cpufreq-cap.service).
- The host reaches the LAN through WSL2 in NAT mode over wired gigabit Ethernet; the push is an
  outbound ssh, so Docker's published ports are not on its path.

## Metrics

### Runs 1-7 (one call each)

| Run | Board | Image | Load applied | Longest off the panel |
|---|---|---|---|---|
| 1 | bench | `a47f215` | ≥ 1.0 MB/s (passed) | 4.5 s |
| 2 | bench | `e0b3363` | 0.67 MB/s | 32.0 s |
| 3 | bench | `e0b3363` | 0.29 MB/s | 32.8 s |
| 4 | bench | `afcbaa3` | 0.40 MB/s | 40.9 s |
| 5 | bench | `e0b3363` | 0.35 MB/s | 48.9 s |
| 6 | bench | `e0b3363` | 0.51 MB/s | 28.8 s |
| 7 | prod | `a47f215` | ≥ 1.0 MB/s (passed) | 3.8 s |

### Run 8

| Part | Direction, cipher | MB/s | Board CPU idle | Host ping under load | Sender TCP (`ss`) |
|---|---|---|---|---|---|
| baseline | idle | — | 14 % (WPE 57 %, kiosk-browser 14 %) | avg 9.6 ms | — |
| push | host to board, default | 0.396 | 0-24 % | avg 165 ms, max 1,125 ms, 0 % loss | 1.4-2.0 MB unacked, rtt 2.8-5.4 s, receive window 2.36 MB, never receive-window limited, no retransmits |
| pull | board to host, default | 0.298 | 0-38 % | — | — |
| AES push | host to board, aes128-ctr | 1.459 | 0 % | avg 29.6 ms, 1 of 60 lost | — |

The baseline also read: 900 MHz cap, `ondemand`; under-voltage alarm 0; 42.8 C; signal -56 dBm at 2457 MHz;
`iw` rx/tx bitrate 5.5 MBit/s; `/data/config` hashes equal to prod's.

### Run 9

| Arm | Cipher | MB/s | rx bitrate before -> after (MBit/s) |
|---|---|---|---|
| A1 | default | 1.769 | 13.0 -> 39.0 |
| B | aes128-ctr | 1.670 | 39.0 -> 58.5 |
| A2 | default | 2.339 | 58.5 -> 39.0 |

### Run 10

| Push | MB/s | rx bitrate, 2 s samples (MBit/s) | Board CPU idle | tx failed |
|---|---|---|---|---|
| 1 | 2.155 | 19.5-58.5 | 0 % at full rate | 289 -> 303 |
| 2 | 2.082 | 6.5-52 | 0-58 % | 304 -> 323 |
| 3 | 0.768 | 13-52 for ~12 s, then 5.5 to the end | 0 % while fast; 37-72 % at 5.5 | 323 -> 564 |
| 4 | 0.494 | 5.5 throughout (once 2.0) | mostly 40-60 % | 564 |

Bench `kiosk-soak`, hourly median `load1` (`analyze.py soak`; samples at 15 min of uptime or more). On the evenings TST008 passed: 23 Nov 18h 1.54; 24 Nov 18h 2.10, 20h 2.26, 21h 2.43. Before the 25 Nov morning step: 04h-07h 0.30-0.56. In general: low overnight,
1.3-2.5 from about 08:00 into the night, on every day from 22 to 25 Nov; overnight hours read mostly 0.2-0.8, higher only in hours with a reboot or a test run.

### Run 12

| | Time | rx / tx bitrate (MBit/s) | tx failed |
|---|---|---|---|
| before | 21:00:34 | 13.0 / 19.5 | 573 |
| call | 21:05:40-21:07:53 | not read | — |
| after | 21:08:00 | 19.5 / 21.6 | 602 |

Load applied 0.57 MB/s; 29.5 s off the panel.

### Run 13 (21:03:54-21:21:09, 102 samples; `analyze.py watch`)

| rx bitrate (MBit/s) | samples |
|---|---|
| 72.2 | 88 |
| 39.0 | 5 |
| 26.0 | 1 |
| 19.5 | 5 |
| 6.5 | 3 (21:07:47, 21:17:36, 21:19:38) |

tx failed 4 in all 102; 2457 MHz in all 102; signal -32 to -36 dBm. Same AP as the bench.

### Run 14

Prod `kiosk-soak`, 25 Nov: `load1` 0.1-1.1 from 03:28 to 07:38 (median about 0.3), about 1.5-2.5 from 07:43, with a dip at 15:46-16:22.

## Findings

| Hypothesis | Disposition | Decided by |
|---|---|---|
| The kernel change on the branch | dropped | run 4: main's kernel INVALID like runs 5-6 |
| The image's userland, the test code or the runner | dropped | run 4's image is run 1's plus commits to tests, tools and docs and a full-size rootfs; `git diff a47f215 e0b3363 -- tests/` is empty; the runner's version string is the same in runs 1 and 6 |
| The host's sending path | dropped | run 7 passed over it at 19:46; run 8's AES push and runs 9-10 carried 1.46-2.34 MB/s over it |
| The ssh cipher | dropped | run 9: default 1.77 and 2.34 MB/s around aes128-ctr 1.67 |
| The board's CPU clock, throttling or heat | dropped | run 8's baseline |
| The board's `/data` configuration | dropped | run 8's baseline: `config.json` and `kiosk.conf` hash-equal to prod's |
| The kiosk page's CPU load | dropped | runs 10 and 14: the same daily step stood on the evenings TST008 passed (23 Nov 18:51, 24 Nov 18:14, 20:14, 21:07: hourly medians 1.54-2.43) |
| The board's CPU cannot decrypt the push | dropped | run 10: at 5.5 MBit/s the CPU is 40-60 % idle and the push is slow; at full rate it is saturated and the push reaches 2.1 MB/s |
| The bench's radio link | **confirmed as a cause of slow pushes; open as the cause of every INVALID** | run 10: the rate follows the AP-to-bench rate inside one push; run 8: 5.5 MBit/s before the 0.40 MB/s push; run 12 is the counter-case, slow at 13-19.5 MBit/s edges with no failure burst |
| The AP or the channel as a whole | **open** | run 13: prod on the same AP and channel held 72.2 MBit/s with no failures through the bench's slow call (run 12); but two of prod's three 6.5 MBit/s samples fall inside run 12's call and 15 s after a bench ssh stall at 21:17 |

The sender's state in run 8 places the queue: the push was never receive-window limited and 1.4-2.0 MB
sat unacknowledged at 3-5 s round trips, so the data waited before the board's TCP stack, on the link,
not in the board's socket.

The records do not hold the radio rate, the failed-transmission counters or the negotiated cipher, so
an INVALID cannot be read as the air from its own record.

## Changes configured as a result

None yet. The two-board watch decides between the bench's own link and channel events the bench's lower
margin cannot absorb; the fix differs (the bench's placement, antenna or local interference, against
the AP's channel), and TST008's floor stays at 1.0 MB/s either way. A follow-up ticket records the
board's receive rate, failed and retried transmissions and wlan0 byte counts at each edge of the call,
with their deltas, so the next INVALID carries its own evidence.

`analyze.py` computes every number taken from a capture here (`soak`, `watch`, `pair`). Every one-off script named above is committed in this directory as it ran, with the bench's address
replaced by `${BENCH}` and the board's hostname by `<hostname>`; their comments name local scheduling
notes that are not in this repository.
