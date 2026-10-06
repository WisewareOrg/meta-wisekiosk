#!/usr/bin/env python3
"""Self-test for analyze-boot-cpu-io.py's handling of a journal that lacks
the browser-probe milestones. Run by hand -- not wired into just guards or
ci-guards.sh.

    analyze-boot-cpu-io-test.py    -- every case, both directions

THE CONTRACT THIS PINS: a sample's matching journal can carry the five
systemd-target milestones (t_expect, t_fs, t_basic, t_wlan, t_online) and
"Started Kiosk browser" (t_kiosk) without carrying either SURFMS milestone
(t_exec: "SURFMS uptime_at_exec", t_loaded: "SURFMS load_finished") -- the
browser's own probe never ran, or uses a different payload format. When
that happens:

  (a) a stderr line names the missing milestones:
      "missing browser milestones: t_exec, t_loaded"
  (b) each browser-phase window ("Xorg -> surf exec", "surf -> load_finished")
      is reported as unavailable, not with DEFAULT_WINDOWS' hardcoded
      figures -- printed as "<name padded to 22><unavailable>", the
      smallest form consistent with report()'s existing per-phase row
      (name left-justified in the same column, data after it).
  (c) the five non-browser phases are still reported normally, from the
      real journal-derived windows.
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

PASS, FAIL = [], []


def case(name, got, want):
    (PASS if got == want else FAIL).append(name)
    if got != want:
        print(f"FAIL  {name}\n        want {want!r}\n        got  {got!r}")


# FIELDS, in analyze-boot-cpu-io.py's own order.
FIELDS = ("up user nice sys idle iowait irq softirq "
          "rd_ios rd_ms wr_ios wr_ms inflight io_ticks nrun nproc").split()


def make_fixture(tmp):
    """A sample file and its matching .journal.txt: the five systemd-target
    milestones and "Started Kiosk browser" present, both SURFMS milestones
    absent. Jiffy counters are synthetic but monotonically increasing, which
    is all summarize() needs."""
    sample = tmp / "boot-sample.txt"
    journal = tmp / "boot-sample.journal.txt"

    lines = []
    for t in (0, 1, 2, 3, 4, 5, 6, 7, 65):
        user, nice, sys_, idle, iowait, irq, softirq = 10 * t, 0, 5 * t, 85 * t, 0, 0, 0
        rd_ios = rd_ms = wr_ios = wr_ms = inflight = io_ticks = t
        nrun, nproc = 1, 50
        lines.append(f"{float(t)} {user} {nice} {sys_} {idle} {iowait} {irq} {softirq} "
                     f"{rd_ios} {rd_ms} {wr_ios} {wr_ms} {inflight} {io_ticks} {nrun} {nproc}")
    sample.write_text("# self_cpu_us=1000 late=0 first_sample_s=0.1\n"
                       + "\n".join(lines) + "\n")

    journal.write_text(
        "[    1.000000] Expecting device /sys/subsystem/net/devices/wlan0\n"
        "[    2.000000] Reached target Local File Systems.\n"
        "[    3.000000] Reached target Basic System.\n"
        "[    4.000000] Found device /sys/subsystem/net/devices/wlan0.\n"
        "[    5.000000] Reached target Network is Online.\n"
        "[    6.000000] Started Kiosk browser\n"
    )
    return sample


def run(sample):
    return subprocess.run(
        [sys.executable, str(HERE / "analyze-boot-cpu-io.py"), str(sample)],
        capture_output=True, text=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sample = make_fixture(Path(tmp))
        got = run(sample)

        case("(a) stderr names the missing browser milestones",
             "missing browser milestones: t_exec, t_loaded" in got.stderr.splitlines(),
             True)

        case("(b) 'Xorg -> surf exec' reported unavailable, not from DEFAULT_WINDOWS",
             f"{'Xorg -> surf exec':<22}unavailable" in got.stdout,
             True)
        case("(b) 'surf -> load_finished' reported unavailable, not from DEFAULT_WINDOWS",
             f"{'surf -> load_finished':<22}unavailable" in got.stdout,
             True)

        case("(c) the five non-browser phases are still reported",
             all(name in got.stdout for name in (
                 "kernel + early systemd", "local filesystems", "sysinit -> basic",
                 "waiting for wlan0", "assoc + DHCP")),
             True)
        case("(c) none of the five non-browser phases are marked unavailable",
             any(f"{name:<22}unavailable" in got.stdout for name in (
                 "kernel + early systemd", "local filesystems", "sysinit -> basic",
                 "waiting for wlan0", "assoc + DHCP")),
             False)

    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
