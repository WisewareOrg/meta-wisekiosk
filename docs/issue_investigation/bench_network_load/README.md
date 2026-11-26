# Why TST008<!-- Sustained network load --> could not apply its network load on the bench board

| | |
|---|---|
| **Issue** | #408 TST008<!-- Sustained network load --> cannot apply its network load on the bench board |
| **Status** | open |
| **Opened / concluded** | 2026-11-25 / — |

TST008<!-- Sustained network load --> pushes random 1 MiB blocks from the bench host into `ssh <board>
wc -c` for 60 s and is valid only if the board takes at least 1.0 MB/s. It passed on the bench at 01:39
EST on 25 Nov 2026 and was INVALID on every bench run from 18:17 that day, on two kernels, at 0.29-0.67
MB/s; prod passed at 19:46 over the same host. The kernel change under review is not the cause (runs
4-6). <!-- pending: LINK_ABSTRACT -->

Every finding here rests on a record of the bench driver (`bench test`, docs/testing.md §"Running it").
Records named `<UTC timestamp>Z` are its records, kept on the bench host, not in this repository. All
times EST, 25 Nov 2026.

## Test runs

| Run | Board (role) | Image commit | Test | Record and result |
|---|---|---|---|---|
| 1 | bench · Pi Zero W | `a47f215` | TST008<!-- Sustained network load --> in the suite | 20261125T062415Z: passed, 4.5 s off the panel |
| 2 | bench · Pi Zero W | `e0b3363` | TST008<!-- Sustained network load --> in a `-k` run | 20261125T225710Z: INVALID, 0.67 MB/s, 32.0 s off, 41.5 s after a power cut |
| 3 | bench · Pi Zero W | `e0b3363` | TST008<!-- Sustained network load -->, skip-build | 20261126T000054Z: INVALID, 0.29 MB/s, 32.8 s off |
| 4 | bench · Pi Zero W | `afcbaa3` | TST008<!-- Sustained network load -->, skip-build | 20261126T002708Z: INVALID, 0.40 MB/s, 40.9 s off (main's kernel) |
| 5 | bench · Pi Zero W | `e0b3363` | TST008<!-- Sustained network load -->, skip-build | 20261126T003329Z: INVALID, 0.35 MB/s, 48.9 s off |
| 6 | bench · Pi Zero W | `e0b3363` | TST008<!-- Sustained network load -->, skip-build | 20261126T003601Z: INVALID, 0.51 MB/s, 28.8 s off |
| 7 | prod · Pi Zero W | `a47f215` | TST008<!-- Sustained network load -->, skip-build | prod 20261126T004619Z: passed, 3.8 s off |
| 8 | bench · Pi Zero W | `6a34d6f` | TST008<!-- Sustained network load --> with its radio record, skip-build of `d554898` | 20261126T031531Z: INVALID, 0.39 MB/s, 42.4 s off; radio properties below |

<!-- pending: LINK_RUN_ROWS, from the link diagnostic's records -->

### Runs 1-8 — TST008<!-- Sustained network load -->

- **Procedure:** `bench test <commit> [--skip-build] -- tests/target_suite -k test_sustained_network_load`
  (runs 2-8), or the target suite (run 1). Runs 4-6 are one control: the bench's other slot (`afcbaa3`,
  main's kernel) booted, the test once, back to `e0b3363`, the test twice. Run 8 is the test with the
  radio record this PR adds.
- **Image commits:** each record's `board_commit`.

<!-- pending: LINK_RUNS_SECTION, from the link diagnostic's records -->

## Configuration under test

- The load, its floor and the push: `tests/board/network/__init__.py` (`_LOAD_FLOOR_MB_S`,
  `Network.load`, `Load.confirm_applied`); the call: `tests/target_suite/test_back_on_the_panel.py`
  (`test_sustained_network_load`).
- The diagnostic: `tests/diagnostics/test_link_under_load.py` (`test_link_under_load`), which loads the
  board with the same `Network.load` and samples the board's radio from a loop on the board itself.
- Run 4's image (`afcbaa3`) is run 1's (`a47f215`) plus commits to tests, tools and docs and a
  full-size rootfs, and `git diff a47f215 e0b3363 -- tests/` is empty.

## Metrics

### Run 8 (one call)

| Property | Value |
|---|---|
| `load_mb_s` | 0.39 |
| `radio_signal_before_dbm` / `_after_dbm` | -59 / -57 |
| `radio_tx_failed_delta` | 0 |
| `wlan0_rx_bytes_delta` | 27,480,594 |
| `wlan0_tx_bytes_delta` | 854,655 |
| `radio_window_s` | 120.7 |

<!-- pending: LINK_METRICS, from the link diagnostic's records -->

## Findings

| Hypothesis | Disposition | Decided by |
|---|---|---|
| The kernel change on the branch | dropped | run 4: main's kernel INVALID between runs 5 and 6 on the branch's |
| The image's userland or the test code | dropped | run 4: the image of run 1's pass, with the same test code, INVALID |
| The host's sending path | dropped | run 7: prod passed over the same host and its WSL2 path |

<!-- pending: LINK_FINDINGS, from the link diagnostic's records -->

Hand-run reads of the bench and prod were also made during the investigation (pushes, ssh cipher, CPU
clock, `/data` configuration, idle radio watches). They were not run through the bench driver, are
withdrawn as evidence, and decide nothing here.

Run 8 shows a limit of the radio record: `tx failed` counts only the board's own transmissions, while
the push runs host to board, so a link held at a low downlink rate shows no failures. A zero
`radio_tx_failed_delta` does not clear the link.

## Changes configured as a result

**Code change, in this PR:**

- TST008<!-- Sustained network load -->'s record carries the radio across its call. `Network.radio()`
  (`tests/board/network/__init__.py`) reads, in one `board.run`, the boot id, the station dump's
  connected time, signal and failed transmissions, and wlan0's byte counts; a read that fails is
  returned as its reason, never raised. `test_sustained_network_load` reads it after the panel is up and
  before the load, and again after the load and the watch, both outside the timed window, and records,
  before any assert: `radio_signal_before_dbm`, `radio_signal_after_dbm`, `radio_tx_failed_delta`,
  `wlan0_rx_bytes_delta`, `wlan0_tx_bytes_delta`, `radio_window_s` and, on every run, `load_mb_s`. A
  failed read records `radio_read_error_before` or `_after` and leaves that edge's numbers and every
  delta out; so do a new boot, a counter that went back, or a station whose connected time grew by less
  than the window less 2 s. Nothing is judged from them: the floor, the bound, the load and
  `confirm_applied` are unchanged. The bitrate is not recorded, since at an idle edge it is the last
  frame's rate. Run 8 is its board run.
- `tests/diagnostics/test_link_under_load.py`: the diagnostic behind runs 9-11, named in
  docs/testing.md beside the other diagnostics.

<!-- pending: LINK_OUTCOME, from the link diagnostic's records -->
