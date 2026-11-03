#!/usr/bin/env python3
"""Parses pstore's ftrace-ramoops-0 for the #245 ftrace seed and per-run
reset reads (pstore-ftrace spec §4.6 and §5). Read-only.

A pstore ftrace line (fs/pstore/inode.c pstore_ftrace_seq_show) is:
    CPU:0 ts:48213 c08b65c8  c08b7310  bcm2835_transfer_pio <- bcm2835_irq+0x94/0x214
fields: cpu, ts, ip, parent_ip, func, "<-", parent+offset/size.

`ts` is a per-boot counter that restarts at 0 each boot, so a drop in `ts`
marks a boot boundary; this tool reads only the segment after the LAST
drop (the latest boot's trace).

Seed usage (spec §4.6, PASS iff all six hold):
    ftrace_tail.py seed <ftrace-ramoops-0> <dmesg-ramoops-0> <filter-list-file>

Reset usage (spec §5, no PASS/FAIL -- just the segment and its tail
classification input):
    ftrace_tail.py tail <ftrace-ramoops-0> [n=200]
"""
import sys
import re

LINE = re.compile(
    r"CPU:(\d+)\s+ts:(\d+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+(\S+)\s+<-\s+(\S+)"
)

CHAIN = [
    "write_sysrq_trigger",
    "__handle_sysrq",
    "sysrq_handle_crash",
    "panic",
    "console_verbose",
]


def parent_func(field):
    """'bcm2835_irq+0x94/0x214' -> 'bcm2835_irq'."""
    return field.split("+")[0]


def parse_records(path):
    records = []
    with open(path, errors="replace") as f:
        for line in f:
            m = LINE.search(line)
            if not m:
                continue
            cpu, ts, ip, pip, func, parent = m.groups()
            records.append(
                {
                    "cpu": int(cpu),
                    "ts": int(ts),
                    "ip": ip,
                    "parent_ip": pip,
                    "func": func,
                    "parent": parent_func(parent),
                }
            )
    return records


def last_segment(records):
    """Records after the last ts-drop (the latest boot's trace)."""
    if not records:
        return []
    start = 0
    for i in range(1, len(records)):
        if records[i]["ts"] < records[i - 1]["ts"]:
            start = i
    return records[start:]


def chain_in_tail(tail, filter_funcs):
    """True iff CHAIN appears, in order, as a parent-linked sequence
    ending at the last record of `tail`, with only filter_funcs sitting
    between consecutive links (when filter_funcs is given)."""
    idx = 0
    positions = []
    for i, r in enumerate(tail):
        if idx < len(CHAIN) and r["func"] == CHAIN[idx] and (
            idx == 0 or r["parent"] == CHAIN[idx - 1]
        ):
            positions.append(i)
            idx += 1
    if idx != len(CHAIN):
        return False
    if positions[-1] != len(tail) - 1:
        return False
    if filter_funcs is not None:
        for a, b in zip(positions, positions[1:]):
            for r in tail[a + 1 : b]:
                if r["func"] not in filter_funcs:
                    return False
    return True


def cmd_seed(ftrace_path, dmesg_path, filter_path):
    checks = {}
    try:
        records = parse_records(ftrace_path)
    except FileNotFoundError:
        records = []
    checks["1_present_nonempty"] = len(records) > 0

    seg = last_segment(records) if records else []

    last = seg[-1] if seg else None
    checks["2_final_is_console_verbose_lt_panic"] = bool(
        last and last["func"] == "console_verbose" and last["parent"] == "panic"
    )

    filter_funcs = None
    try:
        with open(filter_path) as f:
            filter_funcs = {l.strip() for l in f if l.strip()}
        filter_funcs |= set(CHAIN)
    except FileNotFoundError:
        pass
    checks["3_chain_in_tail30"] = chain_in_tail(seg[-30:], filter_funcs)

    funcs = [r["func"] for r in seg]
    checks["4_markers_present"] = (
        funcs.count("bcm2835_time_interrupt") >= 1 and funcs.count("devkmsg_write") >= 1
    )

    checks["5_ts_contiguous"] = len(seg) > 0 and all(
        seg[i]["ts"] == seg[i - 1]["ts"] + 1 for i in range(1, len(seg))
    )

    try:
        dmesg_text = open(dmesg_path, errors="replace").read()
    except FileNotFoundError:
        dmesg_text = ""
    checks["6_dmesg_has_sysrq_crash"] = "sysrq triggered crash" in dmesg_text

    for k, v in checks.items():
        print(f"{k}: {'PASS' if v else 'FAIL'}")
    overall = len(checks) == 6 and all(checks.values())
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


def cmd_tail(ftrace_path, n):
    try:
        records = parse_records(ftrace_path)
    except FileNotFoundError:
        print("no ftrace-ramoops-0")
        return 1
    seg = last_segment(records)
    if not seg:
        print("segment empty")
        return 1
    for r in seg[-n:]:
        print(f"ts={r['ts']} {r['func']} <- {r['parent']}")
    funcs = [r["func"] for r in seg[-n:]]
    print(f"-- segment length {len(seg)}, tail {min(n, len(seg))} shown, "
          f"bcm2835_time_interrupt={funcs.count('bcm2835_time_interrupt')} "
          f"devkmsg_write={funcs.count('devkmsg_write')}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("seed", "tail"):
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "seed":
        if len(sys.argv) != 5:
            print(__doc__, file=sys.stderr)
            sys.exit(2)
        sys.exit(cmd_seed(sys.argv[2], sys.argv[3], sys.argv[4]))
    else:
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 200
        sys.exit(cmd_tail(sys.argv[2], n))
