#!/usr/bin/env python3
"""
Parse a Yocto/bitbake buildstats run directory and report where build time went.

Usage:
    python3 parse_buildstats.py <buildstats_run_dir> [bucket_minutes] [chain_n]

A "run dir" is e.g. .../buildstats/20261002222637/ containing one subdir per
recipe (pn-pv-r0) each holding one file per task that actually executed
(do_compile, do_fetch, ...). Tasks restored from sstate cache instead of
executing are logged as <taskname>_setscene -- those are excluded from the
"real work" accounting throughout as restored, not executed, work.

Each task file has lines like:
    Event: TaskStarted
    Started: 1790992663.27
    webkitgtk3-2.44.3-r0: do_compile
    Elapsed time: 21960.33 seconds
    rusage ru_maxrss: 131988
    Child rusage ru_maxrss: 4060000
    Status: PASSED
    Ended: 1791014623.60

Only Started/Ended/Elapsed and the two maxrss fields are extracted; the rest
of rusage/IO is ignored as not needed for this report.
"""
import sys
import os
import re
from collections import defaultdict

FIELD_RE = re.compile(r'^([A-Za-z][A-Za-z0-9_ ]*?):\s*([^\s].*?)\s*$')


def parse_task_file(path):
    """Return dict with started, ended, elapsed, ru_maxrss, child_maxrss, status."""
    data = {}
    try:
        with open(path, 'r', errors='replace') as f:
            for line in f:
                line = line.rstrip('\n')
                m = FIELD_RE.match(line)
                if not m:
                    continue
                key, val = m.group(1), m.group(2)
                if key == 'Started':
                    data['started'] = float(val)
                elif key == 'Ended':
                    data['ended'] = float(val)
                elif key == 'Elapsed time':
                    data['elapsed'] = float(val.split()[0])
                elif key == 'rusage ru_maxrss':
                    data['ru_maxrss'] = int(val)
                elif key == 'Child rusage ru_maxrss':
                    data['child_maxrss'] = int(val)
                elif key == 'Status':
                    data['status'] = val
    except OSError:
        return None
    return data


def scan_run(run_dir):
    """Walk run_dir, return list of task records (real tasks only, setscene excluded)."""
    tasks = []
    setscene_count = 0
    skipped_unparsed = 0
    for entry in sorted(os.scandir(run_dir), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        recipe = entry.name
        for tf in sorted(os.scandir(entry.path), key=lambda e: e.name):
            if not tf.is_file():
                continue
            taskname = tf.name
            if taskname.endswith('.log'):
                continue
            if taskname.endswith('_setscene'):
                setscene_count += 1
                continue
            d = parse_task_file(tf.path)
            if not d or 'started' not in d or 'ended' not in d:
                skipped_unparsed += 1
                continue
            d['recipe'] = recipe
            d['task'] = taskname
            if 'elapsed' not in d:
                d['elapsed'] = d['ended'] - d['started']
            tasks.append(d)
    return tasks, setscene_count, skipped_unparsed


def fmt_hms(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s"


def report(run_dir, bucket_minutes=10, chain_n=20):
    tasks, setscene_count, skipped = scan_run(run_dir)
    if not tasks:
        print(f"No parseable real tasks found in {run_dir}")
        return

    run_start = min(t['started'] for t in tasks)
    run_end = max(t['ended'] for t in tasks)
    wall = run_end - run_start

    # try to read the build_stats summary file at run root, if present
    bs_path = os.path.join(run_dir, 'build_stats')
    bs_summary = None
    if os.path.isfile(bs_path):
        with open(bs_path) as f:
            bs_summary = f.read().strip()

    out = []
    out.append(f"# Buildstats report: {run_dir}")
    out.append("")
    out.append(f"Real (non-setscene) task files parsed: {len(tasks)}")
    out.append(f"Setscene task files (excluded): {setscene_count}")
    out.append(f"Unparsed/skipped files: {skipped}")
    out.append(f"Wall time (first task Started -> last task Ended): {fmt_hms(wall)} ({wall:.1f}s)")

    # ---- the two reporting figures ----
    image_complete = next((t for t in tasks if t['task'] == 'do_image_complete'), None)
    webkit_configure = next(
        (t for t in tasks if t['recipe'].startswith('webkitgtk3-') and t['task'] == 'do_configure'),
        None,
    )
    if image_complete:
        cold_full = image_complete['ended'] - run_start
        out.append(f"Cold full build (first task Started -> do_image_complete Ended): "
                    f"{fmt_hms(cold_full)} ({cold_full:.1f}s)")
    else:
        out.append("Cold full build: no do_image_complete task in this buildstats dir")
    if image_complete and webkit_configure:
        webkit_rebuild = image_complete['ended'] - webkit_configure['started']
        out.append(f"WebKit rebuild (webkitgtk3 do_configure Started -> do_image_complete Ended): "
                    f"{fmt_hms(webkit_rebuild)} ({webkit_rebuild:.1f}s)")
    else:
        out.append("WebKit rebuild: webkitgtk3 do_configure or do_image_complete not in this "
                    "buildstats dir (restored from sstate, or this run did not reach it)")

    if bs_summary:
        out.append("")
        out.append("build_stats (run-root summary file):")
        out.append("```")
        out.append(bs_summary)
        out.append("```")
    out.append("")

    # ---- top 25 recipes by summed real-task elapsed ----
    by_recipe = defaultdict(float)
    by_recipe_taskcount = defaultdict(int)
    for t in tasks:
        by_recipe[t['recipe']] += t['elapsed']
        by_recipe_taskcount[t['recipe']] += 1
    top_recipes = sorted(by_recipe.items(), key=lambda kv: -kv[1])[:25]

    out.append("## Top 25 recipes by summed real-task elapsed time")
    out.append("")
    out.append("| # | recipe | summed elapsed | real tasks | share of wall |")
    out.append("|---|---|---|---|---|")
    for i, (recipe, secs) in enumerate(top_recipes, 1):
        out.append(f"| {i} | {recipe} | {fmt_hms(secs)} ({secs:.0f}s) | {by_recipe_taskcount[recipe]} | {secs/wall*100:.1f}% |")
    out.append("")

    # ---- top 25 individual tasks by elapsed ----
    top_tasks = sorted(tasks, key=lambda t: -t['elapsed'])[:25]
    out.append("## Top 25 individual tasks by elapsed time")
    out.append("")
    out.append("| # | recipe:task | elapsed | ru_maxrss (KB) | child_maxrss (KB) | started (rel to run start) |")
    out.append("|---|---|---|---|---|---|")
    for i, t in enumerate(top_tasks, 1):
        rel_start = t['started'] - run_start
        out.append(
            f"| {i} | {t['recipe']}:{t['task']} | {fmt_hms(t['elapsed'])} ({t['elapsed']:.0f}s) | "
            f"{t.get('ru_maxrss', '-')} | {t.get('child_maxrss', '-')} | {fmt_hms(rel_start)} |"
        )
    out.append("")

    # ---- concurrency buckets ----
    # Two different metrics, both reported because they answer different
    # questions and are easy to conflate:
    #  - "distinct tasks touching window": any task whose [started,ended)
    #    interval overlaps the bucket at all. A burst of 500 near-instant
    #    do_fetch/do_patch tasks inflates this even though they never run
    #    at the same instant -- it answers "how much distinct work landed
    #    in this window", not "how many threads were busy".
    #  - "point-sample concurrency": tasks with started <= bucket_start <
    #    ended, i.e. genuinely in flight at that instant. This is bounded
    #    by BB_NUMBER_THREADS (bitbake worker threads) and is the right
    #    number for "how parallel was the build right now".
    bucket_s = bucket_minutes * 60
    n_buckets = int(wall // bucket_s) + 2
    touch_counts = [0] * n_buckets
    bucket_names = defaultdict(list)
    for t in tasks:
        b0 = int((t['started'] - run_start) // bucket_s)
        b1 = int((t['ended'] - run_start) // bucket_s)
        b0 = max(0, b0)
        b1 = min(n_buckets - 1, b1)
        for b in range(b0, b1 + 1):
            touch_counts[b] += 1
            if len(bucket_names[b]) < 6:
                bucket_names[b].append(f"{t['recipe']}:{t['task']}")

    point_counts = []
    starts = sorted(t['started'] for t in tasks)
    ends = sorted(t['ended'] for t in tasks)
    for b in range(n_buckets):
        instant = run_start + b * bucket_s
        # count tasks active at `instant` via binary search equivalent (linear is fine at this scale)
        cnt = sum(1 for t in tasks if t['started'] <= instant < t['ended'])
        point_counts.append(cnt)

    out.append(f"## Concurrency per {bucket_minutes}-minute bucket")
    out.append("")
    out.append("| bucket (offset from run start) | distinct tasks touching window | point-sample concurrency (threads busy) | sample tasks touching window |")
    out.append("|---|---|---|---|")
    for b in range(n_buckets):
        if touch_counts[b] == 0 and point_counts[b] == 0:
            continue
        t0 = fmt_hms(b * bucket_s)
        t1 = fmt_hms((b + 1) * bucket_s)
        sample = ", ".join(bucket_names[b][:4])
        out.append(f"| {t0}-{t1} | {touch_counts[b]} | {point_counts[b]} | {sample} |")
    out.append("")

    # ---- latest-finishing chain ----
    out.append(f"## Latest-finishing tasks (top {chain_n} by Ended time) -- tail of the critical path")
    out.append("")
    out.append("| # | recipe:task | ended (rel to run start) | started (rel) | elapsed | concurrently running at its start |")
    out.append("|---|---|---|---|---|---|")
    latest = sorted(tasks, key=lambda t: -t['ended'])[:chain_n]
    for i, t in enumerate(latest, 1):
        rel_end = t['ended'] - run_start
        rel_start = t['started'] - run_start
        concurrent = [
            f"{o['recipe']}:{o['task']}"
            for o in tasks
            if o is not t and o['started'] <= t['started'] < o['ended']
        ]
        conc_str = f"{len(concurrent)}: " + ", ".join(concurrent[:5])
        out.append(f"| {i} | {t['recipe']}:{t['task']} | {fmt_hms(rel_end)} | {fmt_hms(rel_start)} | {fmt_hms(t['elapsed'])} | {conc_str} |")
    out.append("")

    # ---- max concurrency seen at any point & mean ----
    max_point = max(point_counts) if point_counts else 0
    nonzero = [c for c in point_counts if c > 0]
    mean_point = sum(nonzero) / len(nonzero) if nonzero else 0
    solo_buckets = sum(1 for c in point_counts if c == 1)
    idle_buckets = sum(1 for c in point_counts if c == 0)
    out.append(f"Max point-sample concurrency (threads busy) in this run: {max_point}")
    out.append(f"Mean point-sample concurrency (over non-idle buckets): {mean_point:.1f}")
    out.append(f"Buckets with exactly 1 task in flight (single-threaded tail): {solo_buckets} of {n_buckets} ({solo_buckets*bucket_minutes} min)")
    out.append(f"Buckets with 0 tasks in flight (dead time / bitbake overhead only): {idle_buckets}")
    out.append("")

    print("\n".join(out))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <buildstats_run_dir> [bucket_minutes] [chain_n]")
        sys.exit(1)
    run_dir = sys.argv[1]
    bucket_minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    chain_n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    report(run_dir, bucket_minutes, chain_n)
