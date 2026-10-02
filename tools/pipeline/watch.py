#!/usr/bin/env python3
"""Live, read-only view of the merge queue and the current pipeline run.

    watch.py [--help]

Reads $PIPELINE_ENV (default ~/.config/wisekiosk/pipeline.env) for
PIPELINE_DRIVER, never writes under it, never touches the device. The only
systemctl calls are read-only `is-active` polls on wisekiosk-pipeline.timer
and .service.

Layout: a header line (driver sha, timer/service state, clock; any DISABLED
reason on a second line in reverse video), then three bordered panes --
the merge queue, the current run (a stage strip plus its phase detail), and
a tail of the active phase's log file, which takes the rest of the screen.

Keys: q quit, j/k or up/down scroll the log, G or End resume following,
p pause/resume refresh.

Exits 2 if PIPELINE_DRIVER cannot be resolved, or if the terminal is smaller
than 70x20.
"""
import curses
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

MIN_COLS, MIN_LINES = 70, 20
QUEUE_REFRESH_S, RUN_REFRESH_S = 30, 5
QUEUE_ROWS_MAX = 10

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

# Display-only consolidation of PHASES for the stage strip: one node per
# visible stage, "rollback"/"rollback-reboot" and the two posted files each
# collapsed to one name.
STAGE_DISPLAY = (
    ("checkout", ("checkout.log",)),
    ("build", ("build.log",)),
    ("delta", ("delta.txt",)),
    ("bundle", ("bundle.log",)),
    ("preflight", ("preflight.log",)),
    ("send", ("send.log",)),
    ("install", ("install.log",)),
    ("reboot", ("reboot.log",)),
    ("smoke", ("testimage.log",)),
    ("render", ("render.log",)),
    ("gpu", ("gpu.log",)),
    ("rollback", ("rollback.log", "rollback-reboot.log")),
    ("posted", ("verdict.txt", "body.md")),
)
INTERNAL_TO_DISPLAY = {
    "checkout": "checkout", "build": "build", "delta": "delta", "bundle": "bundle",
    "preflight": "preflight", "send": "send", "install": "install", "reboot": "reboot",
    "testimage": "smoke", "render": "render", "gpu": "gpu",
    "rollback": "rollback", "rollback-reboot": "rollback", "posted": "posted",
}

TASK_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Running task (\d+) of (\d+)")
STARTED_RE = re.compile(r"NOTE: recipe (\S+): task (do_\S+): Started")
DONE_RE = re.compile(r"NOTE: recipe (\S+): task (do_\S+): (?:Succeeded|Failed)")
ERROR_TASK_RE = re.compile(r"ERROR: (\S+) (do_\S+): ")
VERDICT_RE = re.compile(r"^VERDICT: (.*)$", re.MULTILINE)
QUEUE_REF_RE = re.compile(r"refs/heads/gh-readonly-queue/main/pr-(\d+)-([0-9a-f]+)$")
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
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def timer_active():
    try:
        out = subprocess.run(["systemctl", "--user", "is-active", "wisekiosk-pipeline.timer"],
                              capture_output=True, text=True, timeout=5)
        return out.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def service_active():
    """True while run.sh is executing (is-active reads "activating" or "active")."""
    try:
        out = subprocess.run(["systemctl", "--user", "is-active", "wisekiosk-pipeline.service"],
                              capture_output=True, text=True, timeout=5)
        return out.stdout.strip() in ("active", "activating")
    except (OSError, subprocess.SubprocessError):
        return False


def disabled_reason(driver):
    try:
        lines = (Path(driver) / "local/pipeline/DISABLED").read_text().splitlines()
    except OSError:
        return None
    return lines[1] if len(lines) > 1 else ""


def fetch_queue():
    """(list of {position, state, number, title, eta_s} dicts, None), or
    (None, error string) on gh failure."""
    try:
        out = subprocess.run(["gh", "api", "graphql", "-f", f"query={GRAPHQL_QUERY}"],
                              capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
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
        entries.append({
            "position": node.get("position"),
            "state": node.get("state"),
            "number": pr.get("number"),
            "title": pr.get("title") or "",
            "eta_s": node.get("estimatedTimeToMerge"),
        })
    return entries, None


def queue_refs(driver):
    """{full sha: (PR number, base sha)} for each merge-queue ref."""
    try:
        out = subprocess.run(["git", "-C", driver, "ls-remote", "origin",
                               "refs/heads/gh-readonly-queue/main/*"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return {}
    if out.returncode != 0:
        return {}
    refs = {}
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        sha, ref = parts
        match = QUEUE_REF_RE.search(ref)
        if match:
            refs[sha] = (int(match.group(1)), match.group(2))
    return refs


class QueueWorker:
    """Fetches the queue and its refs on a background thread, on
    QUEUE_REFRESH_S, so a slow gh or git call never blocks the UI loop. A
    failed fetch keeps the last successful queue/refs; snapshot() reports
    their age alongside the latest error, if any."""

    def __init__(self, driver):
        self.driver = driver
        self.lock = threading.Lock()
        self.queue, self.refs, self.error, self.updated_at = [], {}, None, None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            queue, error = fetch_queue()
            with self.lock:
                if queue is not None:
                    self.queue, self.updated_at, self.error = queue, time.time(), None
                    self.refs = queue_refs(self.driver)
                else:
                    self.error = error
            time.sleep(QUEUE_REFRESH_S)

    def snapshot(self):
        with self.lock:
            return list(self.queue), dict(self.refs), self.error, self.updated_at


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


def median_durations(idx, run_dir, limit=5):
    """Up to `limit` non-negative (this file's mtime - previous file's mtime)
    samples from sibling run dirs that have both files."""
    this_name = PHASES[idx][1]
    prev_name = PHASES[idx - 1][1] if idx > 0 else None
    if prev_name is None:
        return []
    durations = []
    try:
        siblings = sorted((d for d in run_dir.parent.iterdir() if d.is_dir() and d != run_dir),
                           key=lambda d: d.stat().st_mtime, reverse=True)
    except OSError:
        siblings = []
    for cand in siblings:
        if len(durations) >= limit:
            break
        this_file, prev_file = cand / this_name, cand / prev_name
        if not this_file.exists() or not prev_file.exists():
            continue
        dur = this_file.stat().st_mtime - prev_file.stat().st_mtime
        if dur < 0:
            continue
        durations.append(dur)
    return durations


def running_tasks(lines, limit=3):
    """"recipe:do_task" for the last `limit` Started tasks with no later
    Succeeded/Failed/ERROR line for that same recipe:task. A setscene
    failure logs no Failed NOTE, only an ERROR line sharing the same
    recipe-PV-PR identifier as Started."""
    done = set()
    started = []
    for line in lines:
        match = DONE_RE.search(line)
        if match:
            done.add(match.group(1, 2))
            continue
        match = ERROR_TASK_RE.search(line)
        if match:
            done.add(match.group(1, 2))
            continue
        match = STARTED_RE.search(line)
        if match:
            started.append(match.group(1, 2))
    return [f"{recipe}:{task}" for recipe, task in started if (recipe, task) not in done][-limit:]


def build_status(log_path, now, idx, run_dir, prev_file):
    """Elapsed is since the previous phase's file (or the run dir's ctime).
    Rate is tasks done since the first logged line, not the absolute count."""
    elapsed = now - (prev_file.stat().st_mtime if prev_file else run_dir.stat().st_ctime)
    elapsed_mins = int(elapsed / 60)
    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError:
        return f"elapsed {elapsed_mins}m, no task count yet  ETA unknown"
    running = running_tasks(lines)
    running_str = f"  running: {', '.join(running)}" if running else ""
    task_lines = [m for m in (TASK_LINE_RE.match(line) for line in lines) if m]
    if not task_lines:
        return f"elapsed {elapsed_mins}m, no task count yet{running_str}  ETA unknown"
    first_ts = time.mktime(time.strptime(task_lines[0].group(1), "%Y-%m-%d %H:%M:%S"))
    first_done = int(task_lines[0].group(2))
    done, total = int(task_lines[-1].group(2)), int(task_lines[-1].group(3))
    rate_elapsed = now - first_ts
    rate = (done - first_done) / rate_elapsed if rate_elapsed > 0 else 0
    remaining_by_rate = (total - done) / rate if rate > 0 else None

    history = median_durations(idx, run_dir)
    remaining_by_history = max(statistics.median(history) - elapsed, 0) if history else None

    bases = [b for b in (remaining_by_rate, remaining_by_history) if b is not None]
    eta = f"ETA ~{int(max(bases) / 60)}m (rough)" if bases else "ETA unknown"
    return f"{done}/{total} tasks, elapsed {elapsed_mins}m{running_str}  {eta}"


def other_eta(idx, prev_file, run_dir, now):
    start = prev_file.stat().st_mtime if prev_file else run_dir.stat().st_ctime
    elapsed_mins = int((now - start) / 60)
    durations = median_durations(idx, run_dir)
    if not durations:
        return f"elapsed {elapsed_mins}m, no history"
    return f"elapsed {elapsed_mins}m, typical ~{int(statistics.median(durations) / 60)}m"


def verdict_text(run_dir):
    try:
        text = (run_dir / "verdict.txt").read_text()
    except OSError:
        return ""
    match = VERDICT_RE.search(text)
    return match.group(1) if match else ""


def phase_detail(run_dir, now, live):
    """(detail text, its log Path or None, internal phase name or None).
    Posted requires verdict.txt or body.md to be the newest phase file,
    not merely present."""
    idx, phase_file, prev_file = current_phase(run_dir)
    name = PHASES[idx][0] if idx is not None else None
    if not live:
        if name == "posted":
            return f"posted: {verdict_text(run_dir)}", phase_file, name
        return "ended: no verdict (baseline build, or aborted; see DISABLED)", phase_file, name
    if idx is None:
        return "no phase yet", None, None
    if name == "posted":
        return f"posted: {verdict_text(run_dir)}", phase_file, name
    if name == "build":
        return build_status(phase_file, now, idx, run_dir, prev_file), phase_file, name
    return other_eta(idx, prev_file, run_dir, now), phase_file, name


def stage_strip(run_dir, current_internal_name):
    """[(label, is_current), ...] for each STAGE_DISPLAY node: a done stage's
    file exists and a later stage's does too; the current stage is the one
    phase_detail() is reporting on; everything else is pending."""
    reached = [any((run_dir / f).exists() for f in files) for _n, files in STAGE_DISPLAY]
    current_display = INTERNAL_TO_DISPLAY.get(current_internal_name)
    parts = []
    for i, (name, _files) in enumerate(STAGE_DISPLAY):
        if name == current_display:
            marker, current = "●", True       # current
        elif reached[i] and any(reached[i + 1:]):
            marker, current = "✓", False       # done
        else:
            marker, current = "·", False       # pending
        parts.append((f"{name} {marker}", current))
    return parts


def run_title(run_dir, refs, queue):
    sha = run_dir.name
    info = refs.get(sha)
    if not info:
        return f"Current run: sha {sha[:7]}"
    number, base = info
    title = next((e["title"] for e in queue if e["number"] == number), "")
    return f"Current run: PR #{number}  {title}  sha {sha[:7]}  base {base[:7]}"


def tail_lines(path, n=500):
    try:
        return path.read_text(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def safe_addnstr(win, y, x, text, width, attr=0):
    """addnstr, one column short of the window's own last row."""
    max_y, max_x = win.getmaxyx()
    if y == max_y - 1:
        width = min(width, max_x - x - 1)
    if width > 0:
        win.addnstr(y, x, text, width, attr)


def draw_segments(win, y, x, segments, width):
    col, remaining = x, width
    for text, attr in segments:
        if remaining <= 0:
            break
        chunk = text[: min(len(text), remaining)]
        safe_addnstr(win, y, col, chunk, len(chunk), attr)
        col += len(chunk) + 1
        remaining -= len(chunk) + 1


def bordered(height, width, y, x, title):
    height, width = max(height, 3), max(width, 4)
    win = curses.newwin(height, width, y, x)
    win.erase()
    win.box()
    if title:
        safe_addnstr(win, 0, 2, f" {title} "[: width - 4], width - 4)
    return win


def draw(stdscr, state):
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    header = (f"pipeline-watch   driver {state['sha']}   "
              f"timer {'on' if state['timer_on'] else 'off'}   "
              f"service {'running' if state['service_running'] else 'idle'}   "
              f"{time.strftime('%H:%M:%S', time.localtime(state['refreshed']))}")
    safe_addnstr(stdscr, 0, 0, header, max_x)
    header_h = 1
    if state["disabled"] is not None:
        safe_addnstr(stdscr, 1, 0, f"DISABLED: {state['disabled']}".ljust(max_x),
                     max_x, curses.A_REVERSE)
        header_h = 2
    stdscr.noutrefresh()

    queue = state["queue"] or []
    shown = queue[:QUEUE_ROWS_MAX]
    queue_content_h = max(len(shown), 1)
    queue_h = queue_content_h + 2
    run_h = 4
    log_y = header_h + queue_h + run_h
    log_h = max(max_y - log_y, 0)

    age = state["queue_age"]
    title = (f"Merge queue ({len(queue)} entries, updated {age}s ago)" if age is not None
             else f"Merge queue ({len(queue)} entries)")
    queue_win = bordered(queue_h, max_x, header_h, 0, title)
    content_w = max_x - 4
    if age is None and state["queue_error"]:
        safe_addnstr(queue_win, 1, 2, f"queue: unavailable ({state['queue_error']})", content_w)
    elif age is None:
        safe_addnstr(queue_win, 1, 2, "queue: loading...", content_w)
    elif not queue:
        safe_addnstr(queue_win, 1, 2, "queue: empty", content_w)
    else:
        for i, entry in enumerate(shown):
            building = entry["number"] is not None and entry["number"] == state["building_pr"]
            marker = "▶ " if building else "  "
            eta = f"~{int(entry['eta_s'] / 60)}m" if entry.get("eta_s") else ""
            left = (f"{marker}{entry['position']:<4}#{entry['number']:<6}"
                    f"{entry['state']:<17}{entry['title']}")
            line = left[: content_w - len(eta) - 1].ljust(content_w - len(eta)) + eta
            safe_addnstr(queue_win, 1 + i, 2, line[:content_w], content_w,
                         curses.A_BOLD if building else 0)
    queue_win.noutrefresh()

    run_win = bordered(run_h, max_x, header_h + queue_h, 0, state["run_title"])
    if state["run_dir"]:
        draw_segments(run_win, 1, 2, [(f"{label} ", curses.A_BOLD if cur else 0)
                                       for label, cur in state["stage_parts"]], max_x - 4)
        safe_addnstr(run_win, 2, 2, state["phase_detail"], max_x - 4)
    else:
        safe_addnstr(run_win, 1, 2, "no runs yet", max_x - 4)
    run_win.noutrefresh()

    if log_h > 0:
        if state["paused"]:
            follow_state = "paused"
        elif state["scroll"] == 0:
            follow_state = "following"
        else:
            follow_state = "scrolled"
        log_name = state["log_path"].name if state["log_path"] else "log"
        log_win = bordered(log_h, max_x, log_y, 0, f"{log_name}  ({follow_state})")
        lines = state["log_lines"] or []
        visible = log_h - 2
        state["log_visible"] = visible
        if visible > 0 and lines:
            offset = state["scroll"]
            end = len(lines) - offset if offset else len(lines)
            start = max(0, end - visible)
            for i, line in enumerate(lines[start:end]):
                safe_addnstr(log_win, 1 + i, 2, line, max_x - 4)
        log_win.noutrefresh()
    else:
        state["log_visible"] = 0

    curses.doupdate()


def main(stdscr, driver):
    """None on a clean quit, else an error line for the caller to print after
    curses tears down."""
    max_y, max_x = stdscr.getmaxyx()
    if max_x < MIN_COLS or max_y < MIN_LINES:
        return f"watch.py: terminal must be at least {MIN_COLS}x{MIN_LINES}"

    curses.curs_set(0)
    stdscr.timeout(200)

    worker = QueueWorker(driver)
    state = {"sha": "unknown", "disabled": None, "timer_on": False, "service_running": False,
              "queue": [], "refs": {}, "queue_error": None, "queue_age": None,
              "building_pr": None,
              "run_dir": None, "run_title": "no runs yet", "stage_parts": [],
              "phase_detail": "", "log_path": None,
              "log_lines": None, "scroll": 0, "log_visible": 0, "paused": False,
              "refreshed": time.time()}
    last_run = 0

    while True:
        now = time.time()
        if not state["paused"]:
            state["queue"], state["refs"], state["queue_error"], updated_at = worker.snapshot()
            state["queue_age"] = int(now - updated_at) if updated_at else None

        if not state["paused"] and now - last_run >= RUN_REFRESH_S:
            state["sha"] = driver_sha(driver)
            state["disabled"] = disabled_reason(driver)
            state["timer_on"] = timer_active()
            live = service_active()
            state["service_running"] = live
            run_dir = newest_run_dir(driver)
            state["run_dir"] = run_dir
            refs = state["refs"]
            if run_dir is None:
                state["run_title"] = "no runs yet"
                state["stage_parts"], state["phase_detail"], state["log_path"] = [], "", None
                state["log_lines"], state["building_pr"] = None, None
            else:
                state["run_title"] = run_title(run_dir, refs, state["queue"])
                state["building_pr"] = (refs.get(run_dir.name) or (None,))[0]
                detail, log_path, internal_name = phase_detail(run_dir, now, live)
                state["phase_detail"] = detail
                state["log_path"] = log_path
                state["stage_parts"] = stage_strip(run_dir, internal_name)
                state["log_lines"] = tail_lines(log_path) if log_path else None
            state["refreshed"] = now
            last_run = now

        draw(stdscr, state)

        key = stdscr.getch()
        if key == ord("q"):
            return None
        if key in (ord("j"), curses.KEY_DOWN):
            state["scroll"] = max(0, state["scroll"] - 1)
        elif key in (ord("k"), curses.KEY_UP) and state["log_lines"]:
            max_scroll = max(0, len(state["log_lines"]) - state["log_visible"])
            state["scroll"] = min(max_scroll, state["scroll"] + 1)
        elif key in (ord("G"), curses.KEY_END):
            state["scroll"] = 0
        elif key == ord("p"):
            state["paused"] = not state["paused"]


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    main_env_path = os.path.expanduser(os.environ.get("PIPELINE_ENV",
                                                        "~/.config/wisekiosk/pipeline.env"))
    main_driver = load_driver(main_env_path)
    if not main_driver:
        print(f"watch.py: PIPELINE_DRIVER not found via {main_env_path}", file=sys.stderr)
        sys.exit(2)
    main_error = curses.wrapper(main, main_driver)
    if main_error:
        print(main_error, file=sys.stderr)
        sys.exit(2)
