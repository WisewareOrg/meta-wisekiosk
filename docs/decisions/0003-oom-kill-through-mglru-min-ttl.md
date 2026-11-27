# 0003 — End memory-exhaustion thrash with a kernel OOM kill via MGLRU `min_ttl_ms`

**Status:** accepted
**Decided:** 2026-11-21 (PR #322 #257 Performance baseline)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-27 — first written, from the `kiosk-hardware` README (#422 Documentation map).

## Context

On this board, memory exhaustion is a thrash, not a kill. Code pages refault from the SD card and
anonymous pages compress into zram, and both count as reclaim progress, so the kernel's ordinary OOM
killer never runs. PID 1 is starved, misses the 14 s hardware watchdog ping, and the SoC resets with
no kernel message: the panel goes dark, and nothing on the board says why.

What a remedy has to meet: it acts from inside the kernel, because whatever starves PID 1 starves a
userspace watcher too; it sees file-page thrash, not only low free memory; it acts inside the 14 s
watchdog window; and it reaches a board by update, without a WebKit rebuild or a write to the shared
`/boot`.

## Decision

**`kiosk-hardware` writes `1000` to `/sys/kernel/mm/lru_gen/min_ttl_ms` at boot.** With
multi-generation LRU, `kswapd` — a kernel thread userspace starvation cannot stop — compares the age
of the oldest file-page generation with `min_ttl_ms`; a younger generation means the working set is
evicted faster than the limit allows, and the kernel calls `out_of_memory()` (`mm/vmscan.c`,
`lru_gen_age_node()`; `Documentation/admin-guide/mm/multigen_lru.rst`, "Thrashing prevention").

The thrash then ends in a kill the kernel logs at `pr_err`, which reaches the journal and, across a
reset, pstore's console record. The browser and the backend both restart on any exit, so the panel
comes back the way it does after the browser is killed.

`1000` is the value the kernel document names. Seeded on the bench (PR #322 #257 Performance
baseline), an anonymous-memory hog is killed and logged with no reset, and an unkillable tmpfs hog
produces a loop of kills, with no reset, until its files are removed.

## Alternatives considered

- **`vm.panic_on_oom=1` with pstore, alone.** Acts only once the OOM killer is invoked, and under
  thrash the hang comes first.
- **earlyoom.** Userspace, so the same starvation reaches it; and it keys on available memory and
  swap, which cannot see file-page thrash.
- **systemd-oomd.** Needs systemd's `PACKAGECONFIG` changed, which rebuilds WebKit, and PSI enabled on
  the kernel command line on the shared `/boot`, which an update cannot reach.
- **Sizing zram or swap differently.** Moves when the thrash starts; does not stop it.
- **Hung-task or soft-lockup tuning.** Neither fires inside the 14 s watchdog window.

## Consequences

- A process holding memory it cannot give back is killed repeatedly rather than the board resetting;
  the kills are in the journal.
- The setting is a `tmpfiles.d` line in the rootfs, so it travels in an update and falls back with
  its slot.
- Nothing userspace decides which process dies; the kernel's OOM scoring does.

**Premise that would reopen this:** systemd-oomd becoming reachable without its costs — a systemd
`PACKAGECONFIG` change that does not rebuild WebKit, and PSI enabled without a write to the shared
`/boot`.
