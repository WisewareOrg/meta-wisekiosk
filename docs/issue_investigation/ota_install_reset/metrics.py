#!/usr/bin/env python3
"""Per-run metrics for #245, over one or more target_suite records.

    metrics.py <records/TS> [<records/TS> ...]

For each record, reads the install item's first setup-phase TestReport and
prints one line: the install window duration (capture started -> capture
stopped), the max gap between consecutive [stats] lines inside that window,
the max gap between consecutive hb245 heartbeats (any stream), the minimum
wdt= seen, every distinct PID1 state other than S seen (each with its
wchan, first occurrence, deduplicated -- a run can show more than one, and
not all are the same kind of event), and the total seconds PID1 spent in
state D (summed between consecutive heartbeat samples where the earlier
one reads p1=D).

Read-only; writes nothing. One row per run -- never aggregated across runs.
"""
import json
import re
import sys
from datetime import datetime

LINE_RE = re.compile(r"^(\S+) \[(\w+)\] (.*)$")
HB_RE = re.compile(r"hb245 \S+.*?wdt=(\d+) p1=(\S+) p1wchan=(\S*) p1majflt=(\d+)")


def ts(s):
    return datetime.fromisoformat(s)


def install_sections(record):
    with open(f"{record}/report.jsonl") as f:
        for line in f:
            d = json.loads(line)
            if d.get("$report_type") != "TestReport" or d.get("when") != "setup":
                continue
            sections = dict(d.get("sections", []))
            if "capture started" in sections.get("Captured stderr setup", ""):
                return sections.get("Captured stdout setup", ""), sections["Captured stderr setup"]
    return None, None


def one(record):
    out, err = install_sections(record)
    if out is None:
        print(f"record={record} NO INSTALL ITEM FOUND")
        return

    started = stopped = None
    for line in err.splitlines():
        if "capture started" in line:
            started = ts(line.split()[0])
        if "capture stopped" in line:
            stopped = ts(line.split()[0])
    window = (stopped - started).total_seconds() if started and stopped else None

    stats_times = []
    hb_times = []
    hb_samples = []
    for line in out.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        t, tag, rest = ts(m.group(1)), m.group(2), m.group(3)
        if rest.startswith("MemFree") or " MemFree" in rest:
            stats_times.append(t)
        hb = HB_RE.search(rest)
        if hb:
            hb_times.append(t)
            hb_samples.append((t, int(hb.group(1)), hb.group(2), hb.group(3)))

    def max_gap(times):
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        return max(gaps) if gaps else None

    min_wdt = min((w for _, w, _, _ in hb_samples), default=None)

    non_s = []
    seen = set()
    for t, _, p1, wchan in hb_samples:
        if p1 != "S" and (p1, wchan) not in seen:
            seen.add((p1, wchan))
            non_s.append((p1, wchan))

    d_seconds = 0.0
    for (t1, _, p1a, _), (t2, _, _, _) in zip(hb_samples, hb_samples[1:]):
        if p1a == "D":
            d_seconds += (t2 - t1).total_seconds()

    print(
        f"record={record} window={window} max_stats_gap={max_gap(stats_times)} "
        f"max_hb_gap={max_gap(hb_times)} min_wdt={min_wdt} "
        f"non_s_p1={non_s} p1_d_seconds={d_seconds:.1f}"
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    for record in sys.argv[1:]:
        one(record)
