#!/usr/bin/env python3
"""Assemble, redact, cap and post the pipeline run report.

    report.py build --map <path> --limit <n> --verdict <file> --delta <file>
                     [--results [<label>=]<file> ...] [--log [<label>=]<file> ...]
        -- assemble one run's redacted body, capped at --limit, on stdout
    report.py check --map <path>
        -- read a candidate report body on stdin
    report.py post --sha <sha> --state {pending,success,failure,error}
                    --map <path> --description <text> [--pr <n> --body <file>]
        -- post a commit status; with --pr, also --body as a PR comment

build: rc 1 if the body cannot fit --limit; rc 2 on a bad argument, a missing
input, invalid --results JSON, a results file not shaped like oeqa's output,
or private key material anywhere in the raw (uncapped) inputs; nothing on
stdout unless rc 0.
check: rc 0 clean; rc 1 identity found or PARTIAL; rc 2 private-key header or a tool/git failure.
post: redacts and checks --description and --body against --map the same way
`check` does, refusing rc 2 on a hit or a PARTIAL before anything is sent;
rc 1 if gh fails; rc 2 on a bad argument.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent

# git's per-invocation scope -- exported to a hook and to anything it runs,
# and these outrank `git -C <path>`, so a command meant for a different
# checkout would silently read this one instead. Hand list, not derived from
# git itself: `check` must survive a missing or broken git with rc 2, not a
# crash at report.py's own import time from a subprocess call to compute it.
GIT_SCOPE = frozenset((
    "GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR", "GIT_CONFIG", "GIT_PREFIX"))


def git_env(**overrides):
    """The ambient environment with git's per-invocation scope removed."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_SCOPE}
    env.update(overrides)
    return env


# scrub-identity.py is loaded lazily, on first use, and only by the code
# paths that need it (build's redaction; never check's, which only shells
# out to it as a separate process) -- so a load failure there cannot break
# check's "only its four constants" guarantee either.
_scrub_identity_module = None


def _scrub_identity():
    global _scrub_identity_module
    if _scrub_identity_module is None:
        spec_name, filename = "scrub_identity", "scrub-identity.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location(spec_name, TOOLS / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _scrub_identity_module = module
    return _scrub_identity_module


PRIVATE_KEY = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')

STATES = ("pending", "success", "failure", "error")
STATUS_CONTEXT = "bench-pipeline"
DESCRIPTION_MAX = 140


def refuse(reason):
    print(f"could not tell: {reason}", file=sys.stderr)
    return 2


# --- shared: the identity map -----------------------------------------

def load_map_rows(map_path):
    """[(key, value)] for every non-empty, non-public.* row in map_path's
    ```identity fence. Format owner: local/device-identity.md §"Format"."""
    sid = _scrub_identity()
    text = map_path.read_text(encoding="utf-8")
    rows, inside = [], False
    for line in text.splitlines():
        if not inside:
            if sid.FENCE_OPEN.match(line):
                inside = True
            continue
        if sid.FENCE_CLOSE.match(line):
            break
        m = sid.MAP_ROW.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if key.startswith(sid.PUBLIC_NS) or not value:
            continue
        rows.append((key, value))
    return rows


def _redact_known(text, rows):
    """Every map value replaced by <key>, longest value first, case-
    insensitive, in one pass -- so an earlier replacement's own <key> token
    is never itself rescanned and matched against a shorter value."""
    if not rows:
        return text
    ordered = sorted(rows, key=lambda row: -len(row[1]))
    value_to_key = {}
    for key, value in ordered:
        value_to_key.setdefault(value.lower(), key)
    pattern = re.compile(
        "|".join(re.escape(value) for _key, value in ordered), re.IGNORECASE)
    return pattern.sub(lambda m: f"<{value_to_key[m.group(0).lower()]}>", text)


def redact(text, rows):
    text = _redact_known(text, rows)
    for _label, pattern, _remedy in _scrub_identity().PATTERNS:
        text = pattern.sub("<redacted>", text)
    return text


def result_dict(data):
    """The case->status dict from oeqa's `{<result-id>: {configuration, result}}`
    shape or a bare `{configuration, result}`, or {} if data is not shaped
    like either."""
    if not isinstance(data, dict):
        return {}
    result = data.get("result")
    if isinstance(result, dict):
        return result
    for value in data.values():
        if isinstance(value, dict):
            inner = value.get("result")
            if isinstance(inner, dict):
                return inner
    return {}


# --- build --------------------------------------------------------------

def split_label(value, default):
    if "=" in value:
        label, _, path = value.partition("=")
        return label, path
    return default, value


def parse_build_args(argv):
    """((map, limit, verdict, delta, results_specs, log_specs), None), or
    (None, reason)."""
    opts = {"map": None, "limit": None, "verdict": None, "delta": None}
    results, logs = [], []
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        if flag in ("--map", "--limit", "--verdict", "--delta"):
            if not rest:
                return None, f"{flag} takes a value"
            opts[flag[2:]] = rest.pop(0)
        elif flag == "--results":
            if not rest:
                return None, "--results takes a value"
            results.append(rest.pop(0))
        elif flag == "--log":
            if not rest:
                return None, "--log takes a value"
            logs.append(rest.pop(0))
        else:
            return None, f"{flag!r} is not an option this reads"

    missing = [k for k in ("map", "limit", "verdict", "delta") if opts[k] is None]
    if missing:
        return None, "missing required: " + " ".join(f"--{m}" for m in missing)

    try:
        limit = int(opts["limit"])
    except ValueError:
        return None, f"--limit {opts['limit']!r} is not an integer"

    results_specs = [split_label(v, "results") for v in results]
    log_specs = [split_label(v, None) for v in logs]
    return (opts["map"], limit, opts["verdict"], opts["delta"],
            results_specs, log_specs), None


LOG_TRUNCATED_NOTE = "  (log truncated; full log in the run dir)"
RESULTS_LOG_STRIPPED_NOTE = "  (log stripped; see the run dir)"


def render_results(entries):
    if not entries:
        return ""
    multi = len(entries) > 1
    lines = []
    for entry in entries:
        heading = (f"## Test results — {entry['label']}" if multi
                  else "## Test results")
        lines.append(heading)
        lines.append("")
        for case_id, info in result_dict(entry["data"]).items():
            status = info.get("status", "?")
            lines.append(f"- {case_id}: {status}")
            log = info.get("log")
            if log:
                lines.append("  ```")
                for logline in log.splitlines():
                    lines.append("  " + logline)
                lines.append("  ```")
            elif info.get("_log_stripped"):
                lines.append(RESULTS_LOG_STRIPPED_NOTE)
        lines.append("")
    return "\n".join(lines)


DELTA_TRUNCATED_NOTE = "\n\n(delta truncated; full delta in the run dir)\n"
DELTA_TRUNCATED_LINES = 200
DIFF_HEADER = re.compile(r'^diff --git ', re.MULTILINE)
DIFF_PLUS = re.compile(r'^\+(?!\+\+)', re.MULTILINE)
DIFF_MINUS = re.compile(r'^-(?!--)', re.MULTILINE)


def delta_summary_fallback(text):
    """A one-line stand-in for `git apply --stat`, used only when the delta
    text does not parse as a patch (git absent, or not a real diff)."""
    files = len(DIFF_HEADER.findall(text))
    plus = len(DIFF_PLUS.findall(text))
    minus = len(DIFF_MINUS.findall(text))
    return f"{files} files changed, +{plus}/−{minus}"


def delta_stat(text):
    """git's own --stat summary for a unified diff's text, read from stdin
    so no working tree or repository is needed; the hand-rolled one-line
    fallback if git cannot parse it."""
    try:
        result = subprocess.run(["git", "apply", "--stat"], input=text,
                                capture_output=True, text=True, env=git_env())
    except OSError:
        return delta_summary_fallback(text)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.rstrip("\n")
    return delta_summary_fallback(text)


def build_body(verdict_text, delta, results_entries, log_entries):
    parts = [
        "## Verdict", "", verdict_text.rstrip("\n"), "",
        "## Artifact delta", "", "```diff", delta["text"].rstrip("\n"), "```", "",
        render_results(results_entries),
    ]
    for entry in log_entries:
        parts += [f"## Log — {entry['label']}", "", "```",
                 *entry["lines"], "```"]
        if len(entry["lines"]) < entry["total_lines"]:
            parts.append(LOG_TRUNCATED_NOTE)
        parts.append("")
    return "\n".join(parts)


def cap(verdict_text, delta, results_entries, log_entries, limit, rows):
    """The assembled, redacted body within `limit`, or None if it cannot
    fit. Redaction runs on the whole assembled body, every pass, so no
    field (a case id, a status, a log label) can be forgotten. Truncates
    log_entries, results_entries' log fields and delta["text"] in place."""
    while True:
        body = redact(build_body(verdict_text, delta, results_entries,
                                 log_entries), rows)
        if len(body) <= limit:
            return body

        progressed = False
        for entry in log_entries:
            if entry["lines"]:
                entry["lines"].pop(0)
                progressed = True
                break
        if progressed:
            continue

        for entry in results_entries:
            for info in result_dict(entry["data"]).values():
                if "log" in info:
                    del info["log"]
                    info["_log_stripped"] = True
                    progressed = True
                    break
            if progressed:
                break
        if progressed:
            continue

        if not delta.get("truncated"):
            stat = delta_stat(delta["text"])
            truncated_lines = delta["text"].splitlines()[:DELTA_TRUNCATED_LINES]
            delta["text"] = (stat + "\n\n" + "\n".join(truncated_lines)
                            + DELTA_TRUNCATED_NOTE)
            delta["truncated"] = True
            continue

        return None


def cmd_build(argv):
    parsed, why = parse_build_args(argv)
    if why:
        return refuse(why)
    (map_arg, limit, verdict_path, delta_path,
     results_specs, log_specs) = parsed

    try:
        rows = load_map_rows(Path(map_arg))
    except (OSError, UnicodeDecodeError) as exc:
        return refuse(str(exc))

    try:
        verdict_text = Path(verdict_path).read_text(encoding="utf-8")
        delta_text = Path(delta_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return refuse(str(exc))
    delta = {"text": delta_text}

    results_entries = []
    for label, path in results_specs:
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return refuse(str(exc))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return refuse(f"{path}: not valid JSON ({exc})")
        if not isinstance(data, dict):
            return refuse(f"{path}: not a JSON object")
        for case_id, info in result_dict(data).items():
            if not isinstance(info, dict):
                return refuse(f"{path}: {case_id!r}'s value is not a JSON object")
        results_entries.append({"label": label, "data": data})

    log_entries = []
    for label, path in log_specs:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return refuse(str(exc))
        lines = text.splitlines()
        log_entries.append({"label": label or Path(path).name,
                            "lines": lines, "total_lines": len(lines)})

    raw_body = build_body(verdict_text, delta, results_entries, log_entries)
    if PRIVATE_KEY.search(raw_body):
        return refuse("private key material in the raw input")

    body = cap(verdict_text, delta, results_entries, log_entries, limit, rows)
    if body is None:
        print("cannot fit within --limit even after truncating log sections, "
              "stripping results log fields, and truncating the delta",
              file=sys.stderr)
        return 1

    sys.stdout.write(body)
    return 0


# --- check ----------------------------------------------------------------

# check's fixed stderr reasons.
REASON_PRIVATE_KEY = "private key material"
REASON_IDENTITY_FOUND = "identity found"
REASON_IDENTITY_PARTIAL = "identity check PARTIAL"
REASON_TOOL_FAILURE = "tool failure"

IDENTITY_FOUND_MARKER = "IDENTITY IN A TRACKED FILE"


def _tool_failure():
    print(REASON_TOOL_FAILURE, file=sys.stderr)
    return 2


def _check_body(body, map_arg):
    """(rc, reason) -- (0, None) clean; (1, REASON_IDENTITY_FOUND or
    REASON_IDENTITY_PARTIAL); (2, REASON_PRIVATE_KEY or REASON_TOOL_FAILURE)."""
    if PRIVATE_KEY.search(body):
        return 2, REASON_PRIVATE_KEY

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        init = subprocess.run(["git", "init", "-q", str(tmp_path)],
                              env=git_env(), capture_output=True, text=True)
        if init.returncode != 0:
            return 2, REASON_TOOL_FAILURE

        (tmp_path / "report-body.md").write_text(body, encoding="utf-8")
        add = subprocess.run(["git", "-C", str(tmp_path), "add", "report-body.md"],
                             env=git_env(), capture_output=True, text=True)
        if add.returncode != 0:
            return 2, REASON_TOOL_FAILURE

        local_dir = tmp_path / "local"
        local_dir.mkdir()
        (local_dir / "device-identity.md").symlink_to(Path(map_arg).resolve())

        scan = subprocess.run(
            [sys.executable, str(TOOLS / "scrub-identity.py"), "--check", str(tmp_path)],
            env=git_env(), capture_output=True, text=True)

    if scan.returncode == 0:
        return 0, None
    if scan.returncode == 1:
        if "PARTIAL" in scan.stdout:
            return 1, REASON_IDENTITY_PARTIAL
        if IDENTITY_FOUND_MARKER in scan.stdout:
            return 1, REASON_IDENTITY_FOUND
        # Some other rc-1 exit (an uncaught exception in scrub-identity.py,
        # e.g. --map pointing at a directory) is a tool fault, not a finding.
        return 2, REASON_TOOL_FAILURE
    return 2, REASON_TOOL_FAILURE


def cmd_check(argv):
    try:
        return _cmd_check(argv)
    except Exception:
        return _tool_failure()


def _cmd_check(argv):
    map_arg = None
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        if flag == "--map":
            if not rest:
                return _tool_failure()
            map_arg = rest.pop(0)
        else:
            return _tool_failure()
    if map_arg is None:
        return _tool_failure()

    body = sys.stdin.read()
    rc, reason = _check_body(body, map_arg)
    if reason is not None:
        print(reason, file=sys.stderr)
    return rc


# --- post -------------------------------------------------------------

def cmd_post(argv):
    flags = {"--sha": "sha", "--state": "state", "--description": "description",
            "--pr": "pr", "--body": "body", "--map": "map"}
    opts = {v: None for v in flags.values()}
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        key = flags.get(flag)
        if key is None:
            return refuse(f"{flag!r} is not an option this reads")
        if not rest:
            return refuse(f"{flag} takes a value")
        opts[key] = rest.pop(0)

    missing = [k for k in ("sha", "state", "description", "map") if opts[k] is None]
    if missing:
        return refuse("missing required: " + " ".join(f"--{m}" for m in missing))
    if opts["state"] not in STATES:
        return refuse(f"--state must be one of {', '.join(STATES)}")
    if bool(opts["pr"]) != bool(opts["body"]):
        return refuse("--pr and --body must be given together")

    try:
        rows = load_map_rows(Path(opts["map"]))
    except (OSError, UnicodeDecodeError) as exc:
        return refuse(str(exc))

    try:
        description = redact(opts["description"], rows)
        _, reason = _check_body(description, opts["map"])
    except Exception:
        reason = REASON_TOOL_FAILURE
    if reason is not None:
        return refuse(f"description: {reason}")
    description = description[:DESCRIPTION_MAX]

    body_path = None
    if opts["body"]:
        try:
            body_text = Path(opts["body"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return refuse(str(exc))
        try:
            body_text = redact(body_text, rows)
            _, reason = _check_body(body_text, opts["map"])
        except Exception:
            reason = REASON_TOOL_FAILURE
        if reason is not None:
            return refuse(f"body: {reason}")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8")
        tmp.write(body_text)
        tmp.close()
        body_path = tmp.name

    try:
        target_url = None
        if opts["pr"]:
            comment = subprocess.run(
                ["gh", "pr", "comment", opts["pr"], "--body-file", body_path],
                capture_output=True, text=True)
            if comment.returncode != 0:
                print(f"gh pr comment failed: {comment.stderr.strip()}", file=sys.stderr)
                return 1
            out = comment.stdout.strip().splitlines()
            target_url = out[-1] if out else None

        api_args = ["gh", "api", "-X", "POST", f"repos/:owner/:repo/statuses/{opts['sha']}",
                   "-f", f"state={opts['state']}", "-f", f"context={STATUS_CONTEXT}",
                   "-f", f"description={description}"]
        if target_url:
            api_args += ["-f", f"target_url={target_url}"]

        status = subprocess.run(api_args, capture_output=True, text=True)
        if status.returncode != 0:
            print(f"gh api statuses failed: {status.stderr.strip()}", file=sys.stderr)
            return 1
        return 0
    finally:
        if body_path is not None:
            try:
                os.unlink(body_path)
            except OSError:
                pass


def main():
    argv = sys.argv[1:]
    if argv == ["--help"]:
        print(__doc__.strip())
        return 0
    if not argv or argv[0] not in ("build", "check", "post"):
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    mode, rest = argv[0], argv[1:]
    if mode == "build":
        return cmd_build(rest)
    if mode == "check":
        return cmd_check(rest)
    return cmd_post(rest)


if __name__ == "__main__":
    sys.exit(main())
