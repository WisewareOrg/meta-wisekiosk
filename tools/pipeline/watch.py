#!/usr/bin/env python3
"""Live, read-only view of the merge queue and the current pipeline run.

    watch.py [--help]

Reads $PIPELINE_ENV (default ~/.config/wisekiosk/pipeline.env) for
PIPELINE_DRIVER, never writes under it, never calls systemctl, never touches
the device. Screen, top to bottom: header (driver sha, DISABLED reason, last
refresh), the merge queue (refreshed every 30s), the current run's phase and
ETA (refreshed every 5s), and a tail of the active phase's log file.

Keys: q quit, j/k or up/down scroll the log, G or End resume following,
p pause/resume refresh.

Exits 2 if PIPELINE_DRIVER cannot be resolved, or if the terminal is smaller
than 60x15.
"""
import curses
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

MIN_COLS, MIN_LINES = 60, 15
QUEUE_REFRESH_S, RUN_REFRESH_S = 30, 5

# (phase name, log file written for it) in tools/pipeline/run.sh's order.
PHASES = (
    ("checkout", "checkout.log"),
    ("build", "build.log"),
    ("delta", "delta.txt"),
    ("bundle", "bundle.log"),
    ("preflight", "preflight.log"),
    ("send", "send.log"),
    ("install", "install.log"),
    ("reboot", "reboot.log"),
    ("testimage", "testimage.log"),
    ("render", "render.log"),
    ("gpu", "gpu.log"),
    ("rollback", "rollback.log"),
    ("rollback-reboot", "rollback-reboot.log"),
    ("posted", "verdict.txt"),
    ("posted", "body.md"),
)

TASK_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Running task (\d+) of (\d+)")
VERDICT_RE = re.compile(r"^VERDICT: (.*)$", re.MULTILINE)
GRAPHQL_QUERY = (
    '{ repository(owner:"WisewareOrg", name:"meta-wisekiosk") '
    '{ mergeQueue(branch:"main") { entries(first:20) '
    '{ nodes { position state estimatedTimeToMerge '
    'pullRequest { number title } } } } } }'
)


def load_driver(env_path):
    """PIPELINE_DRIVER from env_path's KEY=value lines, or None."""
    try:
        lines = Path(env_path).read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("PIPELINE_DRIVER="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def driver_sha(driver):
    try:
        out = subprocess.run(["git", "-C", driver, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except OSError:
        return "unknown"


def disabled_reason(driver):
    try:
        lines = (Path(driver) / "local/pipeline/DISABLED").read_text().splitlines()
    except OSError:
        return None
    return lines[1] if len(lines) > 1 else ""


def fetch_queue():
    """(entry display strings, None) or (None, error string) on gh failure."""
    try:
        out = subprocess.run(["gh", "api", "graphql", "-f", f"query={GRAPHQL_QUERY}"],
                              capture_output=True, text=True, timeout=15)
    except OSError as exc:
        return None, str(exc).splitlines()[0]
    if out.returncode != 0:
        return None, (out.stderr or "gh failed").splitlines()[0]
    try:
        nodes = json.loads(out.stdout)["data"]["repository"]["mergeQueue"]["entries"]["nodes"]
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"unexpected response: {exc}"
    entries = []
    for node in nodes:
        pr = node.get("pullRequest") or {}
        entries.append(f"{node.get('position')}  #{pr.get('number')}  "
                        f"{node.get('state')}  {pr.get('title', '')}")
    return entries, None


def newest_run_dir(driver):
    try:
        dirs = [d for d in (Path(driver) / "local/pipeline/runs").iterdir() if d.is_dir()]
    except OSError:
        return None
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


def current_phase(run_dir):
    """(PHASES index, its log Path, the previous phase's Path or None) for the
    newest-mtime phase file present, or (None, None, None) if none exist."""
    best = None
    for idx, (_name, fname) in enumerate(PHASES):
        path = run_dir / fname
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if best is None or mtime >= best[0]:
            best = (mtime, idx, path)
    if best is None:
        return None, None, None
    _mtime, idx, path = best
    prev = run_dir / PHASES[idx - 1][1] if idx > 0 else None
    return idx, path, (prev if prev and prev.exists() else None)


def build_eta(log_path, now):
    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError:
        return "elapsed 0m, no task count yet"
    matches = [m for m in (TASK_LINE_RE.match(line) for line in lines) if m]
    if not matches:
        mins = int((now - log_path.stat().st_mtime) / 60) if log_path.exists() else 0
        return f"elapsed {mins}m, no task count yet"
    first_ts = time.mktime(time.strptime(matches[0].group(1), "%Y-%m-%d %H:%M:%S"))
    done, total = int(matches[-1].group(2)), int(matches[-1].group(3))
    elapsed = now - first_ts
    rate = done / elapsed if elapsed > 0 else 0
    eta_mins = int((total - done) / rate / 60) if rate > 0 else 0
    return f"{done}/{total} tasks, elapsed {int(elapsed / 60)}m, ETA ~{eta_mins}m"


def other_eta(idx, phase_file, prev_file, run_dir, now):
    start = prev_file.stat().st_mtime if prev_file else phase_file.stat().st_mtime
    elapsed_mins = int((now - start) / 60)
    this_name = PHASES[idx][1]
    prev_name = PHASES[idx - 1][1] if idx > 0 else None
    durations = []
    try:
        siblings = sorted((d for d in run_dir.parent.iterdir() if d.is_dir() and d != run_dir),
                           key=lambda d: d.stat().st_mtime, reverse=True)
    except OSError:
        siblings = []
    for cand in siblings:
        if len(durations) >= 5:
            break
        this_file = cand / this_name
        prev_cand = cand / prev_name if prev_name else None
        if not this_file.exists() or not (prev_cand and prev_cand.exists()):
            continue
        durations.append(this_file.stat().st_mtime - prev_cand.stat().st_mtime)
    if not durations:
        return f"elapsed {elapsed_mins}m, no history"
    return f"elapsed {elapsed_mins}m, typical ~{int(statistics.median(durations) / 60)}m"


def verdict_text(run_dir):
    try:
        text = (run_dir / "verdict.txt").read_text()
    except OSError:
        return ""
    match = VERDICT_RE.search(text)
    if match:
        return match.group(1)
    return text.strip().splitlines()[-1] if text.strip() else ""


def phase_line(run_dir, now):
    """"PHASE: ..." text for run_dir's current phase, and its log Path (or None)."""
    idx, phase_file, prev_file = current_phase(run_dir)
    if idx is None:
        return "no phase yet", None
    name = PHASES[idx][0]
    if name == "posted":
        return f"PHASE: posted {verdict_text(run_dir)}", phase_file
    if name == "build":
        return f"PHASE: build  {build_eta(phase_file, now)}", phase_file
    return f"PHASE: {name}  {other_eta(idx, phase_file, prev_file, run_dir, now)}", phase_file


def tail_lines(path, n=500):
    try:
        return path.read_text(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def draw(stdscr, state):
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    top = [f"pipeline-watch  driver {state['sha']}"
           + (f"  DISABLED: {state['disabled']}" if state["disabled"] is not None else "")
           + f"  refreshed {time.strftime('%H:%M:%S', time.localtime(state['refreshed']))}",
           "queue:"]
    if state["queue_error"]:
        top.append(f"queue: unavailable ({state['queue_error']})")
    elif not state["queue"]:
        top.append("queue: empty")
    else:
        top.extend(state["queue"])
    top.append("")
    top.append(f"run {state['run_dir'].name}" if state["run_dir"] else "no runs yet")
    if state["run_dir"]:
        top.append(state["phase_line"])
    top.append("")

    row = 0
    for line in top:
        if row >= max_y:
            break
        stdscr.addnstr(row, 0, line, max_x)
        row += 1

    lines = state["log_lines"] or []
    visible = max_y - row
    if visible > 0 and lines:
        offset = state["scroll"]
        end = len(lines) - offset if offset else len(lines)
        start = max(0, end - visible)
        for i, line in enumerate(lines[start:end]):
            stdscr.addnstr(row + i, 0, line, max_x)

    stdscr.noutrefresh()
    curses.doupdate()


def main(stdscr):
    env_path = os.path.expanduser(os.environ.get("PIPELINE_ENV",
                                                   "~/.config/wisekiosk/pipeline.env"))
    driver = load_driver(env_path)
    if not driver:
        curses.endwin()
        print(f"watch.py: PIPELINE_DRIVER not found via {env_path}", file=sys.stderr)
        return 2
    max_y, max_x = stdscr.getmaxyx()
    if max_x < MIN_COLS or max_y < MIN_LINES:
        curses.endwin()
        print(f"watch.py: terminal must be at least {MIN_COLS}x{MIN_LINES}", file=sys.stderr)
        return 2

    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(200)

    state = {"sha": driver_sha(driver), "disabled": disabled_reason(driver),
              "queue": [], "queue_error": None, "run_dir": None, "phase_line": "",
              "log_lines": None, "scroll": 0, "refreshed": time.time()}
    last_queue = last_run = 0
    paused = False

    while True:
        now = time.time()
        if not paused and now - last_queue >= QUEUE_REFRESH_S:
            state["queue"], state["queue_error"] = fetch_queue()
            state["queue"] = state["queue"] or []
            last_queue = now

        if not paused and now - last_run >= RUN_REFRESH_S:
            run_dir = newest_run_dir(driver)
            state["run_dir"] = run_dir
            if run_dir is None:
                state["phase_line"], state["log_lines"] = "", None
            else:
                state["phase_line"], log_path = phase_line(run_dir, now)
                state["log_lines"] = tail_lines(log_path) if log_path else None
            state["refreshed"] = now
            last_run = now

        draw(stdscr, state)

        try:
            key = stdscr.getch()
        except curses.error:
            key = -1
        if key == ord("q"):
            return 0
        if key == curses.KEY_RESIZE:
            curses.update_lines_cols()
        elif key in (ord("j"), curses.KEY_DOWN):
            state["scroll"] = max(0, state["scroll"] - 1)
        elif key in (ord("k"), curses.KEY_UP) and state["log_lines"]:
            state["scroll"] = min(len(state["log_lines"]), state["scroll"] + 1)
        elif key in (ord("G"), curses.KEY_END):
            state["scroll"] = 0
        elif key == ord("p"):
            paused = not paused


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    sys.exit(curses.wrapper(main))
