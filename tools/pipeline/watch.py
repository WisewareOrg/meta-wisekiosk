#!/usr/bin/env python3
"""Live, read-only view of the merge queue and the current pipeline run.

    watch.py [--help]

Reads the file at $PIPELINE_ENV (default ~/.config/wisekiosk/pipeline.env)
for PIPELINE_DRIVER=<path> and PIPELINE_TREE=<path> lines; PIPELINE_DRIVER
is the pipeline driver checkout this reads from, PIPELINE_TREE the working
tree whose build/buildhistory it checks for a completed baseline build's
tag. Never writes under either, never touches the device. The only
subprocesses besides `git -C <driver> rev-parse` (the header's driver sha)
and `gh api graphql` (the merge queue) are read-only
`systemctl --user is-active` polls on wisekiosk-pipeline.timer and
wisekiosk-pipeline.service, and a read-only
`git -C <tree>/build/buildhistory tag -l` poll for a baseline build's tag.

Screen, top to bottom:
  1. Header: "pipeline-watch", the driver's short HEAD sha, "timer on/off",
     "service running/idle", and the time of the last refresh. A DISABLED
     reason (driver's local/pipeline/DISABLED file) adds a second header
     line in reverse video.
  2. Merge queue, refreshed every QUEUE_REFRESH_S = 30s on a background
     thread: one row per entry -- position, PR number, state, title, and
     GitHub's own ETA as a right-hand "~Xm" column -- up to QUEUE_ROWS_MAX
     = 10 rows. The entry whose head commit matches the current run's sha
     is marked with a bold "▶" while the service is active/activating, or
     the word "next" once it goes idle. An empty queue reads "queue:
     empty"; a `gh` failure reads "queue: unavailable (<its first error
     line>)", shown beside the last successful queue and its age once one
     has ever loaded, in place of the queue before that.
  3. Current run, refreshed every RUN_REFRESH_S = 5s: a stage strip (one
     node per pipeline phase, wrapping onto further rows rather than
     truncating) and a detail line below it -- elapsed time and an ETA for
     an in-progress phase, "posted: <verdict>" for a finished one, "ended:
     no verdict" for one that stopped without posting, or "baseline <sha>
     built" for a completed baseline build. A live `build` phase also
     shows up to 3 running recipe:task names on their own row underneath,
     so they can't push the ETA off the line.
  4. Log pane, the rest of the screen: the tail of the active phase's own
     log file, titled with the file name and following/paused/scrolled,
     following the end by default.

Keys: q quit; j or the down arrow moves the log pane's view toward its live
end, k or the up arrow scrolls it back; G or End jumps back to the live end
and resumes following; p pauses or resumes all refresh.

Exits 2, printing one line to stderr, if PIPELINE_DRIVER cannot be resolved
from the env file, or if the terminal is smaller than 70 columns by 20 rows.
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

# STAGES: (internal name, log file, display name, failure substrings), one
# row per phase in tools/pipeline/run.sh's order.
#   internal name       the phase as run.sh names it; "posted" for both
#                       rows after a run ends (verdict.txt, body.md)
#   log file            the file run.sh writes for that phase, inside a
#                       run directory (<driver>/local/pipeline/runs/<sha>/)
#   display name        the stage-strip label; the two rollback rows and
#                       the two posted rows each share one display name,
#                       collapsing to a single stage-strip node
#   failure substrings  the literal text run.sh's finish() posts to
#                       verdict.txt for this stage's own failure --
#                       "bundle"/"preflight"/"send"/"install"/"build"
#                       failed via run_or_fail()'s "<name> failed", and
#                       "reboot" via "new slot did not boot"; () for a
#                       stage whose failure is read a different way
#                       (smoke via testresults.json, render/gpu via their
#                       own tail log) or not attributed by text at all
STAGES = (
    ("checkout", "checkout.log", "checkout", ()),
    ("build", "build.log", "build", ("build failed",)),
    ("bundle", "bundle.log", "bundle", ("bundle failed",)),
    ("preflight", "preflight.log", "preflight", ("preflight failed",)),
    ("send", "send.log", "send", ("send failed",)),
    ("install", "install.log", "install", ("install failed",)),
    ("reboot", "reboot.log", "reboot", ("did not boot",)),
    ("testimage", "testimage.log", "smoke", ()),
    ("render", "render.log", "render", ()),
    ("gpu", "gpu.log", "gpu", ()),
    ("rollback", "rollback.log", "rollback", ()),
    ("rollback-reboot", "rollback-reboot.log", "rollback", ()),
    ("posted", "verdict.txt", "posted", ()),
    ("posted", "body.md", "posted", ()),
)
INTERNAL_TO_DISPLAY = {name: display for name, _file, display, _subs in STAGES}


def _stage_display():
    """Group STAGES by display name, keeping each name's files together.

    Returns [(display name, (file, ...)), ...], one entry per distinct
    display name, in the order each first appears in STAGES."""
    by_display = {}
    for _name, file, display, _subs in STAGES:
        by_display.setdefault(display, []).append(file)
    return [(display, tuple(files)) for display, files in by_display.items()]


STAGE_DISPLAY = _stage_display()


# {display name: (substring, ...)}, from STAGES' failure-substrings
# column, for every row that has one. No display name currently appears
# on two non-empty rows, so this needs no deduplication.
FAILURE_PATTERNS = {display: subs for _name, _file, display, subs in STAGES if subs}

# "<timestamp> ... Running task N of M (...)", a bitbake progress line.
TASK_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Running task (\d+) of (\d+)")
# "NOTE: recipe R: task T: Started"
STARTED_RE = re.compile(r"NOTE: recipe (\S+): task (do_\S+): Started")
# "NOTE: recipe R: task T: Succeeded" or "...Failed"
DONE_RE = re.compile(r"NOTE: recipe (\S+): task (do_\S+): (?:Succeeded|Failed)")
# "ERROR: R T: ..." -- a bitbake setscene failure logs no Succeeded/Failed line
ERROR_TASK_RE = re.compile(r"ERROR: (\S+) (do_\S+): ")
# The "VERDICT: <text>" line run.sh's finish() writes to verdict.txt
VERDICT_RE = re.compile(r"^VERDICT: (.*)$", re.MULTILINE)
# Gates failed_stages_from_verdict() so a verdict with none of these words
# is never read as a failure.
FAILURE_WORD_RE = re.compile(r"failed|failure|did not|could not|aborted")
# Position, state, ETA, head/base commit oid and PR number/title for each
# entry in this repo's main-branch merge queue.
GRAPHQL_QUERY = (
    '{ repository(owner:"WisewareOrg", name:"meta-wisekiosk") '
    '{ mergeQueue(branch:"main") { entries(first:20) '
    '{ nodes { position state estimatedTimeToMerge '
    'headCommit { oid } baseCommit { oid } '
    'pullRequest { number title } } } } } }'
)


def load_env_value(env_path, key):
    """`key`'s value from env_path's KEY=value lines (leading/trailing
    whitespace and surrounding double quotes stripped).

    Returns None if env_path can't be read or has no such line."""
    try:
        lines = Path(env_path).read_text().splitlines()
    except OSError:
        return None
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"')
    return None


def _run_or_none(cmd, timeout):
    """Run `cmd`.

    Returns its stripped stdout regardless of exit code (`systemctl
    is-active` exits non-zero for "activating" and every other state but
    "active", printing the state to stdout either way), or None if it
    raises (a missing executable, or a timeout past `timeout` seconds)."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def driver_sha(driver):
    """Run `git -C driver rev-parse --short HEAD`.

    Returns its stripped stdout, or "unknown" on failure."""
    return _run_or_none(["git", "-C", driver, "rev-parse", "--short", "HEAD"], 5) or "unknown"


def timer_active():
    """True while `systemctl --user is-active wisekiosk-pipeline.timer`
    reads exactly "active"; False on any other value or failure."""
    return _run_or_none(["systemctl", "--user", "is-active", "wisekiosk-pipeline.timer"], 5) \
        == "active"


def service_active():
    """True while run.sh is executing (is-active reads "activating" or "active").

    `systemctl --user is-active wisekiosk-pipeline.service`: the unit is
    Type=oneshot, so a live run reads "activating" for its whole duration
    and never the bare "active". False on any other value or failure."""
    return _run_or_none(["systemctl", "--user", "is-active", "wisekiosk-pipeline.service"], 5) \
        in ("active", "activating")


def disabled_reason(driver):
    """Read driver's local/pipeline/DISABLED file.

    Returns its second line (the reason), "" if the file has only one
    line, or None if the file doesn't exist."""
    try:
        lines = (Path(driver) / "local/pipeline/DISABLED").read_text().splitlines()
    except OSError:
        return None
    return lines[1] if len(lines) > 1 else ""


def baseline_tag_exists(tree, sha):
    """Whether `git -C <tree>/build/buildhistory tag -l baseline/<sha>`
    lists that tag -- run.sh's own marker for a completed baseline build
    of `sha`. A missing `tree`, a missing buildhistory directory, or a
    git failure all read as no tag.

    Returns a bool."""
    if not tree:
        return False
    out = _run_or_none(
        ["git", "-C", f"{tree}/build/buildhistory", "tag", "-l", f"baseline/{sha}"], 5)
    return bool(out)


def fetch_queue():
    """Run `gh api graphql` with GRAPHQL_QUERY to list the merge queue.

    Returns (entries, None) on success, or (None, error string) if the gh
    call fails or times out (15s), or its JSON doesn't have the expected
    shape. `entries` is a list of dicts, one per queue node that carries a
    pullRequest (a node with none is dropped), each:
      position  int, 1-based queue position
      state     str, GitHub's queue state (e.g. "QUEUED", "AWAITING_CHECKS")
      number    int, the PR number
      title     str, the PR title ("" if GitHub returned none)
      eta_s     int or None, estimatedTimeToMerge in seconds
      head_sha  str or None, the entry's headCommit oid
      base_sha  str or None, the entry's baseCommit oid
    The error string is the first line of gh's stderr (the literal
    "gh failed" if stderr is empty), of the raised exception, or
    "unexpected response: <exc>" if the JSON shape doesn't match."""
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
        if not node:
            continue
        pr = node.get("pullRequest") or {}
        number = pr.get("number")
        if number is None:
            continue
        entries.append({
            "position": node.get("position"),
            "state": node.get("state") or "?",
            "number": number,
            "title": pr.get("title") or "",
            "eta_s": node.get("estimatedTimeToMerge"),
            "head_sha": (node.get("headCommit") or {}).get("oid"),
            "base_sha": (node.get("baseCommit") or {}).get("oid"),
        })
    return entries, None


class QueueWorker:
    """Fetches the merge queue on a background thread, every QUEUE_REFRESH_S.

    Attributes (read via snapshot(), not directly):
      queue       list of entry dicts as fetch_queue() returns; the last
                  successful fetch's result ([] until the first one lands)
      error       str or None, the most recent fetch's error (gh can keep
                  failing after queue was last populated, or can recover)
      updated_at  float or None, time.time() of the last successful fetch
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.queue, self.error, self.updated_at = [], None, None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        """Loop: fetch_queue(), store the result under self.lock, sleep
        QUEUE_REFRESH_S. Any exception fetch_queue() doesn't itself catch
        is caught here and stored as self.error -- its first line (falling
        back to the exception's class name if it has no message) -- rather
        than killing the thread."""
        while True:
            try:
                queue, err = fetch_queue()
            except Exception as exc:
                queue, err = None, (str(exc) or type(exc).__name__).splitlines()[0]
            with self.lock:
                if queue is not None:
                    self.queue = queue
                    self.updated_at = time.time()
                self.error = err
            time.sleep(QUEUE_REFRESH_S)

    def snapshot(self):
        """Return (list(self.queue), self.error, self.updated_at), copied
        under self.lock so the caller never reads a partial update."""
        with self.lock:
            return list(self.queue), self.error, self.updated_at


def newest_run_dir(driver):
    """The most-recently-modified directory under
    driver/local/pipeline/runs/.

    Returns a Path, or None if that directory is missing or empty."""
    try:
        dirs = [d for d in (Path(driver) / "local/pipeline/runs").iterdir() if d.is_dir()]
    except OSError:
        return None
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


def current_phase(run_dir):
    """Find which STAGES entry's file was modified most recently in run_dir.

    Returns (idx, path, prev_path):
      idx        index into STAGES of the phase whose file has the latest
                 mtime among all STAGES files present in run_dir (a tie
                 keeps the later STAGES index)
      path       that file's Path
      prev_path  STAGES[idx - 1]'s file's Path, if it exists; else None
                 (always None when idx == 0)
    Returns (None, None, None) if no STAGES file exists in run_dir."""
    best = None
    for idx, (_name, fname, _display, _subs) in enumerate(STAGES):
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
    prev = run_dir / STAGES[idx - 1][1] if idx > 0 else None
    return idx, path, (prev if prev and prev.exists() else None)


def median_durations(idx, run_dir, limit=5):
    """Sample how long the STAGES[idx] phase has taken in prior runs.

    Scans sibling directories under run_dir's parent, newest mtime first
    (run_dir itself excluded), collecting up to `limit` samples: for each
    sibling where both STAGES[idx]'s file and STAGES[idx - 1]'s file
    exist, the sample is (STAGES[idx] file's mtime - STAGES[idx - 1]
    file's mtime). A sibling missing either file, or giving a negative
    sample (the dir was reused out of order), doesn't count toward the
    limit, and the scan continues to the next sibling.

    Returns a list of up to `limit` floats (seconds), or [] when idx == 0
    (no previous phase to pair with) or no sibling has both files."""
    this_name = STAGES[idx][1]
    prev_name = STAGES[idx - 1][1] if idx > 0 else None
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
    """Which bitbake tasks in `lines` look still in progress.

    Matches three line shapes: STARTED_RE, DONE_RE, and ERROR_TASK_RE. A
    (recipe, task) pair counts as done once a DONE_RE or ERROR_TASK_RE
    line names it; the remaining started pairs, in the order their
    Started line appeared, are formatted "recipe:task".

    Returns the last `limit` such strings (closest to the end of
    `lines`)."""
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


def _phase_start(prev_file, run_dir):
    """The previous phase file's mtime, or run_dir's ctime if there is no
    previous phase."""
    return prev_file.stat().st_mtime if prev_file else run_dir.stat().st_ctime


def build_status(log_path, now, idx, run_dir, prev_file):
    """Elapsed time, task progress and ETA for a live `build` phase.

    Elapsed is `now` minus _phase_start(prev_file, run_dir). Reads
    log_path (build.log) for TASK_LINE_RE's "Running task N of M" lines
    and for running_tasks()'s input. The rate is (tasks done - tasks done
    at the first such line) over the time since that first line's own
    timestamp; "remaining by rate" is (total - done) / rate. "remaining
    by history" is max(median(median_durations(idx, run_dir)) - elapsed,
    0). The ETA shown is whichever of the two is larger, labelled
    "(rough)"; "ETA unknown" if neither is available.

    Returns (line, running_line):
      line          "elapsed Xm, no task count yet  ETA unknown" before
                    any Running-task line is found, else
                    "N/M tasks, elapsed Xm  ETA ~Ym (rough)" (or
                    "...ETA unknown" with no rate and no history)
      running_line  "running: r1:t1, r2:t2, ..." from running_tasks(), or
                    None if none are in progress or log_path can't be read
    """
    elapsed = now - _phase_start(prev_file, run_dir)
    elapsed_mins = int(elapsed / 60)
    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError:
        return f"elapsed {elapsed_mins}m, no task count yet  ETA unknown", None
    running = running_tasks(lines)
    running_line = f"running: {', '.join(running)}" if running else None
    task_lines = [m for m in (TASK_LINE_RE.match(line) for line in lines) if m]
    if not task_lines:
        return f"elapsed {elapsed_mins}m, no task count yet  ETA unknown", running_line
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
    return f"{done}/{total} tasks, elapsed {elapsed_mins}m  {eta}", running_line


def other_eta(idx, prev_file, run_dir, now):
    """Elapsed time and a typical duration for any non-build phase.

    Elapsed is `now` minus _phase_start(prev_file, run_dir). The typical
    duration is the median of median_durations(idx, run_dir), when it
    returns any samples.

    Returns "elapsed Xm, no history" with no samples, else
    "elapsed Xm, typical ~Ym"."""
    elapsed_mins = int((now - _phase_start(prev_file, run_dir)) / 60)
    durations = median_durations(idx, run_dir)
    if not durations:
        return f"elapsed {elapsed_mins}m, no history"
    return f"elapsed {elapsed_mins}m, typical ~{int(statistics.median(durations) / 60)}m"


def verdict_text(run_dir):
    """The text after "VERDICT: " in run_dir's verdict.txt (VERDICT_RE,
    matched anywhere in the file).

    Returns "" if the file is missing or has no such line."""
    try:
        text = (run_dir / "verdict.txt").read_text()
    except OSError:
        return ""
    match = VERDICT_RE.search(text)
    return match.group(1) if match else ""


def smoke_failed(run_dir, checkout_mtime):
    """Whether run_dir's testresults.json (oeqa's JSON test report, copied
    in by run.sh when the device comes back) records any case whose
    status is neither "PASSED" nor "SKIPPED" ("FAILED", "ERROR",
    "UNKNOWN", or anything else all count).

    Returns False if the file is missing, has an mtime before
    `checkout_mtime` (a None `checkout_mtime` skips this check; this
    excludes one left over from an earlier run in a reused run
    directory), or doesn't parse as the expected
    {session: {"result": {case: {"status": ...}}}} shape."""
    path = run_dir / "testresults.json"
    try:
        if checkout_mtime is not None and path.stat().st_mtime < checkout_mtime:
            return False
        sessions = json.loads(path.read_text())
        for session in sessions.values():
            for case in (session.get("result") or {}).values():
                if case.get("status") not in ("PASSED", "SKIPPED"):
                    return True
    except (OSError, ValueError, AttributeError, TypeError):
        return False
    return False


def failed_stages_from_verdict(run_dir, text):
    """Which display stages a posted run's verdict text names as failed.

    Consulted only when `text` matches FAILURE_WORD_RE ("failed",
    "failure", "did not", "could not", "aborted") -- a verdict with none
    of those words is never read as a failure, and this returns an empty
    set without looking any further. When it does, every signal that
    fires is collected (more than one display name can come back, since a
    smoke failure can coincide with a render or gpu failure reported
    separately): smoke_failed() marks "smoke" (and, like every signal
    below, only from a testresults.json no older than checkout.log's own
    mtime); each STAGES row's own "<internal name>.tail.log" existing in
    run_dir, with the same mtime floor, marks its display name -- run.sh
    writes these directly for render/gpu and via stage_logargs() for the
    run_or_fail() stages, but never a reliable one for testimage itself
    (stage_logargs() runs there even on a pass, whenever testresults.json
    is missing), so "testimage" is excluded from this check; and
    FAILURE_PATTERNS' substrings matched against `text`.

    Returns a frozenset of STAGES display names (empty if the gate fails
    or no signal fires)."""
    if not FAILURE_WORD_RE.search(text):
        return frozenset()
    try:
        checkout_mtime = (run_dir / "checkout.log").stat().st_mtime
    except OSError:
        checkout_mtime = None
    failed = set()
    if smoke_failed(run_dir, checkout_mtime):
        failed.add("smoke")
    for name, _file, display, _subs in STAGES:
        if name in ("posted", "testimage"):
            continue
        tail_log = run_dir / f"{name}.tail.log"
        try:
            fresh = checkout_mtime is None or tail_log.stat().st_mtime >= checkout_mtime
        except OSError:
            continue
        if fresh:
            failed.add(display)
    for display, substrings in FAILURE_PATTERNS.items():
        if any(s in text for s in substrings):
            failed.add(display)
    return frozenset(failed)


def phase_detail(run_dir, now, live, tree, disabled):
    """The run pane's detail line(s) for run_dir's current phase.

    `live` is service_active()'s result; `tree` is PIPELINE_TREE's path
    (for baseline_tag_exists()); `disabled` is disabled_reason()'s result
    (None, "", or a reason string).

    A `posted` phase (verdict.txt or body.md is the newest file) is
    reported the same whether or not the service is live: its verdict
    text is matched via failed_stages_from_verdict() (a frozenset of
    STAGES display names, empty when the text names no failure, in which
    case no stage is marked). Otherwise, with the service idle: a
    `build`-newest run with no DISABLED and a matching
    baseline_tag_exists() reads as a completed baseline build (the
    `build` node marked done, not failed); any other idle, unposted run
    reads as ended with no verdict, the newest phase marked failed
    unconditionally (there is no verdict text to gate this case on). With
    the service live: an in-progress `build` phase is delegated to
    build_status(); any other in-progress phase to other_eta(); no phase
    file yet gives "no phase yet".

    Returns (detail, running_line, log_path, internal_name, failed_stages,
    done_display):
      detail          the phase-detail row's text (see above)
      running_line    build_status()'s running-tasks line, or None
      log_path        current_phase()'s matched file Path, or None with
                      no phase yet
      internal_name   the current phase's STAGES[*][0] name, or None
      failed_stages   frozenset of STAGES display names stage_strip()
                      should mark "failed" (possibly more than one, or
                      empty for none)
      done_display    the STAGES display name stage_strip() should mark
                      "done" (a completed baseline build's `build` node),
                      or None"""
    idx, phase_file, prev_file = current_phase(run_dir)
    name = STAGES[idx][0] if idx is not None else None
    if name == "posted":
        text = verdict_text(run_dir)
        return (f"posted: {text}", None, phase_file, name,
                failed_stages_from_verdict(run_dir, text), None)
    if not live:
        if name == "build" and disabled is None and baseline_tag_exists(tree, run_dir.name):
            return f"baseline {run_dir.name[:7]} built", None, phase_file, None, frozenset(), "build"
        marked = INTERNAL_TO_DISPLAY.get(name)
        failed_stages = frozenset({marked}) if marked is not None else frozenset()
        return ("ended: no verdict (baseline build, or aborted; see DISABLED)", None, phase_file,
                name, failed_stages, None)
    if idx is None:
        return "no phase yet", None, None, None, frozenset(), None
    if name == "build":
        detail, running_line = build_status(phase_file, now, idx, run_dir, prev_file)
        return detail, running_line, phase_file, name, frozenset(), None
    return other_eta(idx, prev_file, run_dir, now), None, phase_file, name, frozenset(), None


def _stage_reached(run_dir, files, checkout_mtime):
    """Whether any of `files` (one STAGE_DISPLAY node's file names) counts
    as reached in run_dir.

    A file counts only if its mtime is >= checkout_mtime (a None
    checkout_mtime skips this check; this excludes a file left over from
    a previous run in a reused run directory).

    Returns True if any file in `files` counts, else False."""
    for fname in files:
        path = run_dir / fname
        try:
            st = path.stat()
        except OSError:
            continue
        if checkout_mtime is not None and st.st_mtime < checkout_mtime:
            continue
        return True
    return False


def stage_strip(run_dir, current_internal_name, failed_stages, done_display):
    """One row per STAGE_DISPLAY node, for the run pane's stage strip.

    checkout_mtime is checkout.log's own mtime (None if it doesn't
    exist), passed to _stage_reached() for every node. A node's state is
    "failed" if its display name is in `failed_stages` (phase_detail()'s
    verdict-named or DISABLED-ended failures; more than one node can read
    failed at once), else "done" if it equals `done_display` (a completed
    baseline build's `build` node), else "current" if it equals
    current_internal_name's display name, else "done" if _stage_reached()
    holds for its own files and for any later node's files, else
    "pending".

    Returns [(label, state), ...] in STAGE_DISPLAY order, where label is
    "<display name> <marker>" (✗ failed, ● current, ✓ done, · pending)
    and state is one of "failed", "current", "done", "pending"."""
    try:
        checkout_mtime = (run_dir / "checkout.log").stat().st_mtime
    except OSError:
        checkout_mtime = None
    reached = [_stage_reached(run_dir, files, checkout_mtime) for _n, files in STAGE_DISPLAY]
    current_display = INTERNAL_TO_DISPLAY.get(current_internal_name)
    markers = {"failed": "✗", "current": "●", "done": "✓", "pending": "·"}
    parts = []
    for i, (name, _files) in enumerate(STAGE_DISPLAY):
        if name in failed_stages:
            state = "failed"
        elif name == done_display:
            state = "done"
        elif name == current_display:
            state = "current"
        elif reached[i] and any(reached[i + 1:]):
            state = "done"
        else:
            state = "pending"
        parts.append((f"{name} {markers[state]}", state))
    return parts


def run_title(run_dir, queue):
    """The run pane's border title for run_dir.

    `queue` is the list of entry dicts fetch_queue() returns. Matches
    run_dir's directory name (the run's git sha) against each entry's
    head_sha first, then (if no head_sha matched) each entry's base_sha.

    Returns:
      "Current run: PR #N  <title>  sha <short>"         on a head_sha
                                                          match
      "Current run: baseline <short> for PR #N  <title>" on a base_sha
                                                          match
      "Current run: sha <short>"                         with no match"""
    sha = run_dir.name
    for entry in queue:
        if entry.get("head_sha") == sha:
            return f"Current run: PR #{entry['number']}  {entry['title']}  sha {sha[:7]}"
    for entry in queue:
        if entry.get("base_sha") == sha:
            return f"Current run: baseline {sha[:7]} for PR #{entry['number']}  {entry['title']}"
    return f"Current run: sha {sha[:7]}"


def tail_lines(path, n=500):
    """The last `n` lines of path, decoding errors replaced.

    Returns [] if path can't be read."""
    try:
        return path.read_text(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def safe_addnstr(win, y, x, text, width, attr=0):
    """win.addnstr(y, x, text, width, attr), with `width` capped one
    column short of win's own last row (ncurses raises if a full-width
    write reaches a window's bottom-right cell). Writes nothing if the
    capped width is 0 or less."""
    max_y, max_x = win.getmaxyx()
    if y == max_y - 1:
        width = min(width, max_x - x - 1)
    if width > 0:
        win.addnstr(y, x, text, width, attr)


def draw_segments(win, y, x, segments, width):
    """Write `segments` (a list of (text, attr) pairs) onto row y of win,
    left to right starting at column x, with one blank column between
    each pair. Each segment is truncated to the columns remaining within
    `width`, and no further segment is drawn once none remain."""
    col, remaining = x, width
    for text, attr in segments:
        if remaining <= 0:
            break
        chunk = text[: min(len(text), remaining)]
        safe_addnstr(win, y, col, chunk, len(chunk), attr)
        col += len(chunk) + 1
        remaining -= len(chunk) + 1


def wrap_segments(parts, width):
    """Pack `parts` (a list of (label, state) pairs, e.g. stage_strip()'s
    result) greedily onto lines no wider than `width` columns. Each
    segment is drawn as "label " (one trailing space) and then followed
    by one further blank column (see draw_segments()), so each is counted
    as len(label) + 2 columns.

    Returns [[(label, state), ...], ...], one inner list per output
    line."""
    lines, current, current_w = [], [], 0
    for label, state in parts:
        seg_w = len(label) + 2
        if current and current_w + seg_w > width:
            lines.append(current)
            current, current_w = [], 0
        current.append((label, state))
        current_w += seg_w
    if current:
        lines.append(current)
    return lines


def bordered(height, width, y, x, title):
    """A new curses window at (y, x), at least 3 rows by 4 columns
    (height/width are raised to that floor), erased and boxed. `title`,
    if truthy, is written " <title> ", truncated to width - 4 columns,
    starting at column 2 of the top border.

    Returns the curses window."""
    height, width = max(height, 3), max(width, 4)
    win = curses.newwin(height, width, y, x)
    win.erase()
    win.box()
    if title:
        safe_addnstr(win, 0, 2, f" {title} "[: width - 4], width - 4)
    return win


STAGE_ATTR = {"current": curses.A_BOLD, "done": 0, "pending": 0}


def draw(stdscr, state):
    """Render one frame into stdscr from `state`, then curses.doupdate().

    Reads from `state`:
      sha, timer_on, service_running, refreshed, disabled  the header line
                 and its optional DISABLED second line
      queue, queue_age, queue_error, marker_pr  the merge queue pane:
                 queue is fetch_queue()'s entry-dict list; marker_pr is
                 the PR number to mark (or None), drawn as "▶" while
                 service_running is True, else "next"
      run_dir, run_title, stage_parts, phase_detail, running_line,
      failed_attr  the current-run pane: stage_parts is stage_strip()'s
                 result, failed_attr the curses attribute for a "failed"
                 stage-strip node
      log_path, log_lines, paused, scroll  the log pane: log_lines is
                 tail_lines()'s result, scroll the number of lines back
                 from the end currently shown
    Writes into `state`:
      log_visible  the log pane's visible row count, for the caller to
                 clamp further scrolling against

    A fresh bordered window is built for each pane on every call;
    curses.doupdate() only sends the terminal the cells that actually
    changed since the last call, regardless."""
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    header = (f"pipeline-watch  driver {state['sha']}  "
              f"timer {'on' if state['timer_on'] else 'off'}  "
              f"service {'running' if state['service_running'] else 'idle'}  "
              f"{time.strftime('%H:%M:%S', time.localtime(state['refreshed']))}")
    safe_addnstr(stdscr, 0, 0, header, max_x)
    header_h = 1
    if state["disabled"] is not None:
        safe_addnstr(stdscr, 1, 0, f"DISABLED: {state['disabled']}".ljust(max_x),
                     max_x, curses.A_REVERSE)
        header_h = 2
    stdscr.noutrefresh()

    queue = state["queue"]
    shown = queue[:QUEUE_ROWS_MAX]
    age = state["queue_age"]
    error = state["queue_error"]
    error_row = 1 if (age is not None and error) else 0
    queue_content_h = max(len(shown), 1) + error_row
    queue_h = queue_content_h + 2
    strip_lines = wrap_segments(state["stage_parts"], max_x - 4) if state["run_dir"] else []
    running_extra = 1 if state["running_line"] else 0
    run_h = len(strip_lines) + 3 + running_extra if strip_lines else 4
    log_y = header_h + queue_h + run_h
    log_h = max(max_y - log_y, 0)

    title = (f"Merge queue ({len(queue)} entries, updated {age}s ago)" if age is not None
             else f"Merge queue ({len(queue)} entries)")
    queue_win = bordered(queue_h, max_x, header_h, 0, title)
    content_w = max_x - 4
    if age is None and error:
        safe_addnstr(queue_win, 1, 2, f"queue: unavailable ({error})", content_w)
    elif age is None:
        safe_addnstr(queue_win, 1, 2, "queue: loading...", content_w)
    else:
        if not queue:
            safe_addnstr(queue_win, 1, 2, "queue: empty", content_w)
        else:
            for i, entry in enumerate(shown):
                matched = entry["number"] == state["marker_pr"]
                live_match = matched and state["service_running"]
                marker = "▶" if live_match else ("next" if matched else "")
                eta = f"~{int(entry['eta_s'] / 60)}m" if entry.get("eta_s") else ""
                left = (f"{marker:<5}{entry['position']:<4}#{entry['number']:<6}"
                        f"{entry['state']:<17}{entry['title']}")
                line = left[: content_w - len(eta) - 1].ljust(content_w - len(eta)) + eta
                safe_addnstr(queue_win, 1 + i, 2, line[:content_w], content_w,
                             curses.A_BOLD if live_match else 0)
        if error:
            safe_addnstr(queue_win, 1 + max(len(shown), 1), 2,
                         f"queue: unavailable ({error})", content_w)
    queue_win.noutrefresh()

    run_win = bordered(run_h, max_x, header_h + queue_h, 0, state["run_title"])
    if state["run_dir"]:
        attrs = {**STAGE_ATTR, "failed": state["failed_attr"]}
        for row, line in enumerate(strip_lines, start=1):
            draw_segments(run_win, row, 2, [(f"{label} ", attrs[s]) for label, s in line],
                          max_x - 4)
        safe_addnstr(run_win, len(strip_lines) + 1, 2, state["phase_detail"], max_x - 4)
        if state["running_line"]:
            safe_addnstr(run_win, len(strip_lines) + 2, 2, state["running_line"], max_x - 4)
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


def main(stdscr, driver, tree):
    """Run the TUI's event loop against `driver` (PIPELINE_DRIVER's path)
    and `tree` (PIPELINE_TREE's path, or None if unset).

    Returns immediately, without entering the loop, with a one-line
    "terminal must be at least ..." string if stdscr is smaller than
    MIN_COLS x MIN_LINES. Otherwise starts a QueueWorker, builds the
    state dict draw() reads and writes (see its docstring for the keys),
    and loops, paced by stdscr.timeout(200) (each getch() below waits up
    to 200ms):
      - every iteration, unless state["paused"]: copies the worker's
        latest queue/error/age via QueueWorker.snapshot()
      - every RUN_REFRESH_S seconds, unless state["paused"]: re-reads the
        driver sha, DISABLED reason, timer and service state, the newest
        run directory, and (via phase_detail()/stage_strip()) that run's
        phase detail, running-tasks line and stage strip
      - calls draw(stdscr, state), then reads one key: q returns; j or
        KEY_DOWN decrements state["scroll"] (toward the log's live end);
        k or KEY_UP increments it, capped at the log's length minus its
        visible rows (scrolling back); G or KEY_END resets it to 0
        (resume following); p flips state["paused"]

    Returns None on a clean quit (q); the caller prints the terminal-size
    string above, if returned, after curses tears down."""
    max_y, max_x = stdscr.getmaxyx()
    if max_x < MIN_COLS or max_y < MIN_LINES:
        return f"watch.py: terminal must be at least {MIN_COLS}x{MIN_LINES}"

    curses.curs_set(0)
    stdscr.timeout(200)

    failed_attr = curses.A_BOLD
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED, -1)
        failed_attr = curses.color_pair(1) | curses.A_BOLD

    worker = QueueWorker()
    state = {"sha": "unknown", "disabled": None, "timer_on": False, "service_running": False,
              "queue": [], "queue_error": None, "queue_age": None,
              "marker_pr": None, "failed_attr": failed_attr,
              "run_dir": None, "run_title": "no runs yet", "stage_parts": [],
              "phase_detail": "", "running_line": None, "log_path": None,
              "log_lines": None, "scroll": 0, "log_visible": 0, "paused": False,
              "refreshed": time.time()}
    last_run = 0

    while True:
        now = time.time()
        if not state["paused"]:
            state["queue"], state["queue_error"], updated_at = worker.snapshot()
            state["queue_age"] = int(now - updated_at) if updated_at else None

        if not state["paused"] and now - last_run >= RUN_REFRESH_S:
            state["sha"] = driver_sha(driver)
            state["disabled"] = disabled_reason(driver)
            state["timer_on"] = timer_active()
            live = service_active()
            state["service_running"] = live
            run_dir = newest_run_dir(driver)
            state["run_dir"] = run_dir
            if run_dir is None:
                state["run_title"] = "no runs yet"
                state["stage_parts"], state["phase_detail"], state["running_line"] = [], "", None
                state["log_path"], state["log_lines"], state["marker_pr"] = None, None, None
            else:
                state["marker_pr"] = next((e["number"] for e in state["queue"]
                                            if e.get("head_sha") == run_dir.name), None)
                detail, running_line, log_path, internal_name, failed_stages, done_display = \
                    phase_detail(run_dir, now, live, tree, state["disabled"])
                state["run_title"] = (f"Current run: baseline {run_dir.name[:7]} built"
                                       if done_display is not None
                                       else run_title(run_dir, state["queue"]))
                state["phase_detail"] = detail
                state["running_line"] = running_line
                state["log_path"] = log_path
                state["stage_parts"] = stage_strip(run_dir, internal_name, failed_stages,
                                                    done_display)
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
    main_driver = load_env_value(main_env_path, "PIPELINE_DRIVER")
    if not main_driver:
        print(f"watch.py: PIPELINE_DRIVER not found via {main_env_path}", file=sys.stderr)
        sys.exit(2)
    main_tree = load_env_value(main_env_path, "PIPELINE_TREE")
    main_error = curses.wrapper(main, main_driver, main_tree)
    if main_error:
        print(main_error, file=sys.stderr)
        sys.exit(2)
