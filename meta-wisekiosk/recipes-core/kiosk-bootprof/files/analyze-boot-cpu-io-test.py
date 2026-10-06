#!/usr/bin/env python3
"""Self-test for analyze-boot-cpu-io.py's WPE browser-phase milestones. Run
by hand -- not wired into just guards or ci-guards.sh.

    analyze-boot-cpu-io-test.py    -- every case, both directions

THE CONTRACT THIS PINS: a default WPE boot (no probe) emits two journal
lines that bound ONE browser phase, "kiosk start -> page loaded" --
systemd's "Started Kiosk browser..." (t_kiosk, unchanged from before) and
cog's own "<URL> Loaded successfully." on WEBKIT_LOAD_FINISHED (t_loaded,
replacing the old SURFMS-probe-specific source). The X/surf-era two-phase
split ("Xorg -> surf exec", "surf -> load_finished") and its t_exec
milestone are retired -- no label names X or surf.

  (a) both lines present: the phase reports real wall/busy/idle figures
      spanning t_kiosk to t_loaded, not "unavailable".
  (b) the cog load line absent (t_kiosk present): stderr names the one
      missing milestone ("missing browser milestones: t_loaded"), and the
      phase prints "<name padded to 22>unavailable".
  (c) NO milestone matches at all (not even the five generic ones): the
      same stderr convention fires, naming both ("missing browser
      milestones: t_kiosk, t_loaded") -- the residual gap rev-content
      noted, where journal_windows() fell back to DEFAULT_WINDOWS before
      ever printing anything. The browser phase row never appears with
      fabricated DEFAULT_WINDOWS figures (DEFAULT_WINDOWS carries no
      browser entry at all); the five generic phases still report from
      DEFAULT_WINDOWS, unchanged.

Journal line text for t_kiosk and t_loaded is copied verbatim from
docs/issue_investigation/wpe_evaluation/s3-stall-correlation-run2.txt
(lines 12 and 21); only the bracketed monotonic timestamp is changed, to
land inside this fixture's small sample window.
"""
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

GENERIC_MILESTONES = (
    "[    1.000000] Expecting device /sys/subsystem/net/devices/wlan0\n"
    "[    2.000000] Reached target Local File Systems.\n"
    "[    3.000000] Reached target Basic System.\n"
    "[    4.000000] Found device /sys/subsystem/net/devices/wlan0.\n"
    "[    5.000000] Reached target Network is Online.\n"
)

# Verbatim from s3-stall-correlation-run2.txt:12, timestamp changed to 6.0.
T_KIOSK_LINE = (
    "[    6.000000] <BENCH_HOSTNAME> systemd[1]: Started Kiosk browser: "
    "cog on WPE WebKit, straight to DRM, no display server.\n"
)
# Verbatim from s3-stall-correlation-run2.txt:21, timestamp changed to 7.0.
T_LOADED_LINE = (
    "[    7.000000] <BENCH_HOSTNAME> cog[14629]: "
    "<http://localhost:8080/> Loaded successfully.\n"
)


def make_sample(tmp):
    """A sample file with rows at every integer second 0-7 plus 65 --
    enough for bracket() to straddle any window the fixtures below need.
    Jiffy counters are synthetic but monotonically increasing, which is
    all summarize() needs."""
    sample = tmp / "boot-sample.txt"
    lines = []
    for t in (0, 1, 2, 3, 4, 5, 6, 7, 65):
        user, nice, sys_, idle, iowait, irq, softirq = 10 * t, 0, 5 * t, 85 * t, 0, 0, 0
        rd_ios = rd_ms = wr_ios = wr_ms = inflight = io_ticks = t
        nrun, nproc = 1, 50
        lines.append(f"{float(t)} {user} {nice} {sys_} {idle} {iowait} {irq} {softirq} "
                     f"{rd_ios} {rd_ms} {wr_ios} {wr_ms} {inflight} {io_ticks} {nrun} {nproc}")
    sample.write_text("# self_cpu_us=1000 late=0 first_sample_s=0.1\n"
                       + "\n".join(lines) + "\n")
    return sample


def run(sample):
    return subprocess.run(
        [sys.executable, str(HERE / "analyze-boot-cpu-io.py"), str(sample)],
        capture_output=True, text=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # (a) both milestones present.
        sample_a = tmp / "a.txt"
        make_sample(tmp).rename(sample_a)
        (tmp / "a.journal.txt").write_text(
            GENERIC_MILESTONES + T_KIOSK_LINE + T_LOADED_LINE)
        got_a = run(sample_a)

        case("(a) 'kiosk start -> page loaded' reports real figures, not unavailable",
             "kiosk start -> page loaded" in got_a.stdout
             and f"{'kiosk start -> page loaded':<22}unavailable" not in got_a.stdout,
             True)
        case("(a) no stderr about missing browser milestones",
             "missing browser milestones" in got_a.stderr,
             False)
        case("(a) no label names Xorg or surf",
             "Xorg" in got_a.stdout or "surf" in got_a.stdout.lower(),
             False)

        # (b) t_kiosk present, cog load line absent.
        sample_b = tmp / "b.txt"
        make_sample(tmp).rename(sample_b)
        (tmp / "b.journal.txt").write_text(GENERIC_MILESTONES + T_KIOSK_LINE)
        got_b = run(sample_b)

        case("(b) stderr names the one missing milestone",
             "missing browser milestones: t_loaded" in got_b.stderr.splitlines(),
             True)
        case("(b) 'kiosk start -> page loaded' reported unavailable",
             f"{'kiosk start -> page loaded':<22}unavailable" in got_b.stdout,
             True)
        case("(b) the five generic phases are still reported normally",
             all(name in got_b.stdout for name in (
                 "kernel + early systemd", "local filesystems", "sysinit -> basic",
                 "waiting for wlan0", "assoc + DHCP")),
             True)

        # (c) no milestone at all matches -- not even the five generic ones.
        sample_c = tmp / "c.txt"
        make_sample(tmp).rename(sample_c)
        (tmp / "c.journal.txt").write_text("")
        got_c = run(sample_c)

        case("(c) stderr still names both missing browser milestones",
             "missing browser milestones: t_kiosk, t_loaded" in got_c.stderr.splitlines(),
             True)
        case("(c) 'kiosk start -> page loaded' never appears with fabricated figures",
             "kiosk start -> page loaded" in got_c.stdout,
             False)
        case("(c) the five generic phases still report from DEFAULT_WINDOWS",
             all(name in got_c.stdout for name in (
                 "kernel + early systemd", "local filesystems", "sysinit -> basic",
                 "waiting for wlan0", "assoc + DHCP")),
             True)

    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
