# Why TST008<!-- Sustained network load --> could not apply its network load on the bench board

| | |
|---|---|
| **Issue** | #408 TST008<!-- Sustained network load --> cannot apply its network load on the bench board |
| **Status** | open: cause narrowed to the bench's radio link; the change below makes the next failure carry its own evidence |
| **Opened / concluded** | 2026-11-25 / — |

TST008<!-- Sustained network load --> pushes random 1 MiB blocks from the bench host into `ssh <board>
wc -c` for 60 s and is valid only if the board takes at least 1.0 MB/s. It passed on the bench at 01:39
EST on 25 Nov 2026 and was INVALID six times from 18:17 that day at 0.29-0.67 MB/s, on two kernels. The
kernel, the image, the test code, the runner, the host's sending path, the ssh cipher, the board's CPU
clock and its configuration on `/data` are each ruled out, and so is the board's CPU as the limit. The
push rate follows the bench's Wi-Fi rate while the push runs: 2.1 MB/s while the AP sends to it at
19.5-58.5 MBit/s, and 0.49 MB/s while it sends at 5.5 MBit/s with the board's CPU half idle; one such
episode lasted over a minute. Prod, on the same AP and channel with 24 dB more signal, logged no failed
transmissions over the same minutes. Still open: whether the bench's own link fails or channel events hit
both boards and only the bench falls, and whether an episode sits inside every INVALID call. This change
records the board's radio counters across every TST008<!-- Sustained network load --> call, so the next
INVALID says which.

All times EST. Records named `<UTC timestamp>Z` are bench-runner records (`bench test` output), kept on
the bench host, not in this repository.

## Test runs

| Run | Board (role) | Image commit | Harness / scripts | Result (1 line) |
|---|---|---|---|---|
| 1 | bench · Pi Zero W | `a47f215` | TST008<!-- Sustained network load -->, `tests/target_suite/test_back_on_the_panel.py` — durable | record 20261125T062415Z: passed, 4.5 s off |
| 2 | bench · Pi Zero W | `e0b3363` | TST008<!-- Sustained network load --> — durable | 20261125T225710Z: INVALID, 0.67 MB/s, 32.0 s off, 41.5 s after a power cut |
| 3 | bench · Pi Zero W | `e0b3363` | TST008<!-- Sustained network load --> — durable | 20261126T000054Z: INVALID, 0.29 MB/s, 32.8 s off |
| 4 | bench · Pi Zero W | `afcbaa3` | TST008<!-- Sustained network load --> + `ctl-*.sh` — one-off | 20261126T002708Z: INVALID, 0.40 MB/s, 40.9 s off (main's kernel) |
| 5 | bench · Pi Zero W | `e0b3363` | TST008<!-- Sustained network load --> + `ctl-*.sh` — one-off | 20261126T003329Z: INVALID, 0.35 MB/s, 48.9 s off |
| 6 | bench · Pi Zero W | `e0b3363` | TST008<!-- Sustained network load --> + `ctl-*.sh` — one-off | 20261126T003601Z: INVALID, 0.51 MB/s, 28.8 s off |
| 7 | prod · Pi Zero W | `a47f215` | TST008<!-- Sustained network load --> — durable | prod 20261126T004619Z: passed, 3.8 s off |
| 8 | bench · Pi Zero W | `6a34d6f` | `netread.sh` and its drivers, `net-ss-sample.sh` — one-off | bare pushes: 0.40 MB/s (default cipher), 1.46 (aes128-ctr), 0.30 board to host |
| 9 | bench · Pi Zero W | `6a34d6f` | `net-cipher-aba.sh`, `a103.sh`, `a103-soakcheck.sh` — one-off | default 1.77, aes128-ctr 1.67, default 2.34 MB/s |
| 10 | bench · Pi Zero W | `6a34d6f` | `net-rate-track.sh`, `ratetrack.sh` — one-off | 2.16, 2.08, 0.77, 0.49 MB/s; rate follows the radio rate |
| 11 | bench · Pi Zero W | `6a34d6f` | TST008<!-- Sustained network load --> + `station-read.sh` — one-off | 20261126T015444Z: VOID (a login inside the call) |
| 12 | bench · Pi Zero W | `6a34d6f` | TST008<!-- Sustained network load --> + `station-read.sh`, `net-rerun2.sh` — one-off | 20261126T020536Z: INVALID, 0.57 MB/s, 29.5 s off |
| 13 | prod · Pi Zero W | `a47f215` | `radio-watch.sh` — one-off | 102 samples, tx failed flat at 4 |
| 14 | bench · Pi Zero W | `6a34d6f` | `radio-watch.sh` — one-off | 60 samples: tx failed flat at 76; idle rx bitrate 5.5 or 2.0 MBit/s throughout |
| 15 | prod · Pi Zero W | `a47f215` | `radio-watch.sh` — one-off | 60 samples: tx failed flat at 4; idle rx bitrate 1.0-58.5 MBit/s, 6.5 in 30 |

### Runs 1-7 — TST008<!-- Sustained network load --> as the suite runs it

- **Boards:** bench and prod, Pi Zero W. **Image commits** from each record's `board_commit` and the
  slot reads in `run-control-reads-bench.txt`.
- **Procedure:** `bench test <commit> --skip-build -- -k test_sustained_network_load` (runs 3-7), or
  the suite (runs 1-2). Runs 4-6 are a slot switch on the bench: the other slot (`afcbaa3`, main's
  kernel) booted with `rauc status mark-active` and one reboot, the test once, back to `e0b3363`, the
  test twice; reads before and after each call, none inside it (`ctl-run.sh`).
- **Raw capture:** the records; `run-control-reads-bench.txt` for runs 4-6.

### Run 8 — bare pushes, with the sender's TCP state

- **Procedure** (`netread.sh 1 2 3`, then `4 5`, its arguments naming the parts below; the pull again by
  `netread3b.sh`). *Baseline:* board reads (wireless, `iw dev wlan0 link`, cpufreq, under-voltage alarm,
  temperature, `top`, journal size, `/data/config` hashes) and 20 host pings. *Push:* 30,000,000 B of
  random data from the host into `ssh <board> wc -c`, beside a board `top` (4 x 5 s), 60 host pings and
  `net-ss-sample.sh` (host `ss -tin` every 2.5 s). *Pull:* the reverse direction (`dd if=/dev/zero
  bs=1000000 count=30` on the board). *AES push:* the push with `-c aes128-ctr`. *Baseline again.* The
  host was quiet for the baseline and the push; the pull and the AES push ran beside a kernel compile.
  The pull's first form used `head -c`, which this image's busybox lacks: it sent nothing and is void;
  `netread.sh` holds only the rerun's form.
- **Raw capture:** `run-netread-bench.txt`.

### Run 9 — cipher A/B/A

- **Procedure:** `net-cipher-aba.sh` (wrapped by `a103.sh`): three 30,000,000 B pushes back to back,
  default cipher, `aes128-ctr`, default; `iw station dump` and loadavg before and after each, board
  `top` beside. Beside a kernel compile (printed). Its `ss` sections are empty: the sampler was handed
  `root@<board>` and could not parse it (fixed before run 10).
- **Raw capture:** `run-cipher-aba-bench.txt`.

### Run 10 — push rate against the radio rate

- **Procedure:** `net-rate-track.sh` (wrapped by `ratetrack.sh`): four 30,000,000 B pushes, default
  cipher; beside each, one board ssh samples `iw dev wlan0 station dump` (rx and tx bitrate, tx failed)
  and `top`'s CPU line every 2 s, starting 2 s before the push: a known board load, equal in all four.
  Beside a host build (printed).
- **Raw capture:** `run-rate-track-bench.txt`.

### Runs 11-12 — TST008<!-- Sustained network load --> with the radio read outside the call

- **Procedure:** `station-read.sh` before and after the call, `net-rerun2.sh` for run 12. Run 11's
  "before" read landed 5 s inside the call, so run 11 is void and is not used. Run 12's before read
  ended about 5 min before the call; a before read should end within 60 s of the call's start.
- **Raw capture:** `run-station-reads-bench.txt` and the records.

### Runs 13-15 — the radio with no load

- **Procedure:** `radio-watch.sh <board> <role> <out> <samples>`: one ssh, every 10 s, uptime, rx and tx
  bitrate, tx failed, signal, frequency and loadavg. Run 13 alone on prod (102 samples, 21:03:54-21:21:09);
  runs 14 and 15 on bench and prod at once (60 samples each, both started at 21:54:00, beside a host
  build). The AP prod is associated with was compared with the bench's in shell variables only and
  reported as the same.
- **Raw capture:** `run-radio-watch-prod-2103.txt`, `run-radio-watch-bench-2154.txt`,
  `run-radio-watch-prod-2154.txt`.

Run 13 used `radio-watch.sh` before its output was made line-buffered (`sed -u`), and run 8 used
`net-ss-sample.sh` before it learned to strip a `user@` prefix; the reads are the same. A bench watch
started beside run 13 was killed by its process group and lost all its output to that buffering; it is
not a run here.

## Configuration under test

- The load and its floor: `tests/board/network/__init__.py` (`_LOAD_FLOOR_MB_S = 1.0`,
  `Network.load`, `Load.confirm_applied`); the call: `tests/target_suite/test_back_on_the_panel.py`
  (`test_sustained_network_load`).
- The host ssh client offers `chacha20-poly1305@openssh.com` first (`ssh -G`, OpenSSH 10.2p1); no host
  ssh package change appears in the host's `/var/log/dpkg.log`, and its ssh configuration files predate
  17 Nov 2026.
- The board's CPU is capped at 900 MHz:
  [`kiosk-cpufreq-cap.service`](../../../meta-wisekiosk/recipes-core/kiosk-cpufreq/files/kiosk-cpufreq-cap.service).
- The host reaches the LAN through WSL2 in NAT mode over wired gigabit Ethernet; the push is an
  outbound ssh, so Docker's published ports are not on its path.
- `iw station dump`'s rx bitrate is the rate of the last frame received. On an idle link that can be a
  broadcast or management frame at a basic rate, so an idle read says little about the link; a read taken
  while a push runs is dominated by the push's frames. The failed and retried transmission counters
  integrate over any window.

## Metrics

Runs 1-7 have one number each; the runs table above carries them.

### Run 8

| Part | Direction, cipher | MB/s | Board CPU idle | Host ping under load | Sender TCP (`ss`) |
|---|---|---|---|---|---|
| baseline | idle | — | 14 % (WPE 57 %, kiosk-browser 14 %) | avg 9.6 ms | — |
| push | host to board, default | 0.396 | 0-24 % | avg 165 ms, max 1,125 ms, 0 % loss | 1.4-2.0 MB unacked, rtt 2.8-5.4 s, receive window 2.36 MB, never receive-window limited, no retransmits |
| pull | board to host, default | 0.298 | 0-38 % | — | — |
| AES push | host to board, aes128-ctr | 1.459 | 0 % | avg 29.6 ms, 1 of 60 lost | — |

The baseline also read: 900 MHz cap, `ondemand`; under-voltage alarm 0; 42.8 C; signal -56 dBm at 2457
MHz; rx/tx bitrate 5.5 MBit/s on the idle link; `/data/config` hashes equal to prod's.

### Run 9

| Arm | Cipher | MB/s | rx bitrate before -> after (MBit/s) |
|---|---|---|---|
| A1 | default | 1.769 | 13.0 -> 39.0 |
| B | aes128-ctr | 1.670 | 39.0 -> 58.5 |
| A2 | default | 2.339 | 58.5 -> 39.0 |

### Run 10

Read by hand from `run-rate-track-bench.txt`; each push's first sample is taken before it starts.

| Push | MB/s | rx bitrate during the push (MBit/s) | Board CPU idle during the push | tx failed |
|---|---|---|---|---|
| 1 | 2.155 | 26.0, 19.5 and 58.5 | 16-18 % at its start, then 0 % | 289 -> 303 |
| 2 | 2.082 | 6.5-52 | 0-44 % | 304 -> 323 |
| 3 | 0.768 | 13-52 for about 12 s, then 5.5 to its end | 0 % while fast; 36-72 % at 5.5 | 323 -> 564 |
| 4 | 0.494 | 5.5 in all samples but two: 2.0 once, and 39.0 in the last, about 3 s before its end | 0-72 %, mostly 40-60 % | 564 |

### Run 12

| | Time | rx / tx bitrate (MBit/s), idle | tx failed |
|---|---|---|---|
| before | 21:00:34 | 13.0 / 19.5 | 573 |
| call | 21:05:40-21:07:53 | not read | — |
| after | 21:08:00 | 19.5 / 21.6 | 602 |

Load applied 0.57 MB/s; 29.5 s off the panel.

### Run 13 (`analyze.py watch`)

| rx bitrate (MBit/s) | samples |
|---|---|
| 72.2 | 88 |
| 39.0 | 5 |
| 26.0 | 1 |
| 19.5 | 5 |
| 6.5 | 3 (21:07:47, 21:17:36, 21:19:38) |

tx failed 4 in all 102; 2457 MHz in all 102; signal -32 to -36 dBm (read by hand).

### Runs 14 and 15 (`analyze.py watch`, each run alone)

| | bench (run 14) | prod (run 15) |
|---|---|---|
| samples | 60 | 60 |
| rx bitrate (MBit/s): samples | 5.5: 56; 2.0: 4 | 58.5: 2; 52.0: 1; 39.0: 2; 26.0: 3; 19.5: 11; 13.0: 10; 6.5: 30; 1.0: 1 |
| tx failed | 76 in all 60 | 4 in all 60 |
| signal (dBm, read by hand) | -55 to -58 | -32 to -33 |

All these bitrates are idle reads: no load ran on either board.

### Runs 14 and 15 side by side (`analyze.py pair`)

Each bench sample paired with the nearest prod sample within 5 s: 60 pairs, the largest gap 4 s, none unpaired; at or below 6.5 MBit/s: bench 60, prod 31, both 31.

Neither board logged a failed transmission in the ten minutes. The idle bitrates sit low on both, the
bench's at 5.5 or 2.0 MBit/s in every sample and prod's at or below 6.5 MBit/s in about half; that is
the last frame's rate on links carrying almost nothing, so the pairing of lows shows no event, shared or
otherwise. With no load, the watch did not stress either link.

## Findings

| Hypothesis | Disposition | Decided by |
|---|---|---|
| The kernel change on the branch | dropped | run 4: main's kernel INVALID like runs 5-6 |
| The image's userland, the test code or the runner | dropped | run 4's image is run 1's plus commits to tests, tools and docs and a full-size rootfs; `git diff a47f215 e0b3363 -- tests/` is empty; the runner's version string is the same in runs 1 and 6 |
| The host's sending path | dropped | run 7 passed over it at 19:46; run 8's AES push and runs 9-10 carried 1.46-2.34 MB/s over it |
| The ssh cipher | dropped | run 9: default 1.77 and 2.34 MB/s around aes128-ctr 1.67 |
| The board's CPU clock, throttling or heat | dropped | run 8's baseline |
| The board's `/data` configuration | dropped | run 8's baseline: `config.json` and `kiosk.conf` hash-equal to prod's |
| The board's CPU, under the page and the push together, as the limit | dropped | run 10: at 5.5 MBit/s the CPU is 40-60 % idle and the push is slow; at full rate the CPU is saturated, the page still running, and the push reaches 2.1 MB/s |
| The bench's radio link | **confirmed as a cause of slow pushes; open as the cause of every INVALID** | run 10: the rate follows the AP-to-bench rate inside one push; run 12 is the counter-case: slow, with only 29 failed transmissions across the call (its edge reads are idle reads) |
| The AP or the channel as a whole | **open** | run 13: prod, on the same AP and channel, logged no failed transmission through the bench's slow call (run 12) and the bench's ssh stall at 21:17, though two of its three 6.5 MBit/s idle reads fall within 15 s of those bench events; runs 14-15: neither board failed a transmission over ten idle minutes, so they decide nothing. A load on both boards at once, with the counters read across it, is what would decide it. |

The sender's state in run 8 places the queue: the push was never receive-window limited and 1.4-2.0 MB
sat unacknowledged at 3-5 s round trips, so the data waited before the board's TCP stack, on the link,
not in the board's socket.

The records of runs 1-7 and 11-12 do not hold the radio's counters or the negotiated cipher, so an
INVALID could not be read as the air from its own record.

## Changes configured as a result

**Code change, in this PR:** TST008<!-- Sustained network load -->'s record carries the radio across
its call. `Network.radio()` (`tests/board/network/__init__.py`) reads, in one `board.run`, the boot id,
the station dump's connected time, signal, retried and failed transmissions, and wlan0's byte counts;
a read that fails is returned as its reason, never raised. `test_sustained_network_load` reads it after
the panel is up and before the load starts, and again once the load and the watch have ended, both
outside the timed window, and records, before any assert: `radio_signal_before_dbm`,
`radio_signal_after_dbm`, `radio_tx_retries_delta`, `radio_tx_failed_delta`, `wlan0_rx_bytes_delta`,
`wlan0_tx_bytes_delta`, `radio_window_s` and, on every run, `load_mb_s`. A failed read records
`radio_read_error_before` or `_after` and leaves that edge's numbers and every delta out; so do a new
boot, a counter that went back, or a station whose connected time grew by less than the window less
2 s (a reconnect, which restarts the counters). Nothing is judged from them: the floor, the bound, the
load and `confirm_applied` are unchanged. The bitrate is not recorded, since at an idle edge it is the
last frame's rate. The parse and the window rule were seeded on the host (a valid window, a missing field,
a new boot, a counter that went back, and the reconnect bound from both sides); the board run that shows
the properties in a record is to come and is named here once it has run.

No change to the bench, the AP or the floor: the fix for the link itself differs between the bench's
placement, antenna or local interference and the AP's channel, and the runs above do not yet tell them
apart.

`analyze.py` computes the run 13-15 counts and the pairing; the other tables are read by hand from the
captures named. The captures were masked after the runs, before commit, by replacing MAC and IPv4
addresses, the board's hostname and the network's name; no masking step is committed, since it would
have to carry the values it removes.

Every one-off script named above is committed in this directory as it ran, with these substitutions:
the bench's address by `${BENCH}`, the board's hostname by `<hostname>`, the operators' host paths by
`${ORCH}` (their scratch directory), `${OUT}` (the output directory), `${BENCH_MANAGER}` (the bench
runner) and `${REPO}` (this repository's checkout), and the labels of local scheduling rules in comments
and log lines by `rule`. The four scripts named `net-*.sh` ran under names carrying the test's id, and
the scripts that call them still use those names. Nothing else in them changed.
