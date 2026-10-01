#!/usr/bin/env python3
"""Assemble, redact, cap and post the bench-pipeline run report.

    report.py build --map <path> --limit <n> --verdict <file> --delta <file>
                     [--results [<label>=]<file> ...] [--log [<label>=]<file> ...]
        -- assemble one run's redacted body, capped at --limit, on stdout
    report.py check --map <path>
        -- read a candidate report body on stdin
    report.py post --sha <sha> --state {pending,success,failure,error}
                    --description <text> [--pr <n> --body <file>]
        -- post a commit status; with --pr, also --body as a PR comment

build: rc 1 if the body cannot fit --limit; rc 2 on a bad argument, a missing
input or invalid --results JSON; nothing on stdout unless rc 0.
check: rc 0 clean; rc 1 identity found; rc 2 private-key header or could not tell.
post: rc 1 if gh fails; rc 2 on a bad argument.
"""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent


def _load_by_path(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_scrub_identity = _load_by_path("scrub_identity", "scrub-identity.py")
_layer_currency = _load_by_path("layer_currency", "layer-currency.py")
PATTERNS = _scrub_identity.PATTERNS
git_env = _layer_currency.git_env

FENCE_OPEN = re.compile(r'^```identity\s*$')
FENCE_CLOSE = re.compile(r'^```\s*$')
MAP_ROW = re.compile(r'^\s*([A-Za-z0-9_.]+)\s*=\s*(\S.*?)\s*$')

PRIVATE_KEY = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')

# Format owner: local/device-identity.md §"Format".
PUBLIC_NS = "public."

STATES = ("pending", "success", "failure", "error")
STATUS_CONTEXT = "bench-pipeline"
DESCRIPTION_MAX = 140


def refuse(reason):
    print(f"could not tell: {reason}", file=sys.stderr)
    return 2


# --- shared: the identity map -----------------------------------------

def load_map_rows(map_path):
    """[(key, value)] for every non-empty, non-public.* row in map_path's
    ```identity fence."""
    text = map_path.read_text(encoding="utf-8")
    rows, inside = [], False
    for line in text.splitlines():
        if not inside:
            if FENCE_OPEN.match(line):
                inside = True
            continue
        if FENCE_CLOSE.match(line):
            break
        m = MAP_ROW.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if key.startswith(PUBLIC_NS) or not value:
            continue
        rows.append((key, value))
    return rows


def redact(text, rows):
    for key, value in sorted(rows, key=lambda row: -len(row[1])):
        text = text.replace(value, f"<{key}>")
    for _label, pattern, _remedy in PATTERNS:
        text = pattern.sub("<redacted>", text)
    return text


def result_dict(data):
    """The case->status dict inside a --results JSON, either oeqa's own
    `{<result-id>: {configuration, result}}` shape or a bare
    `{configuration, result}`."""
    if isinstance(data.get("result"), dict):
        return data["result"]
    for value in data.values():
        if isinstance(value, dict) and isinstance(value.get("result"), dict):
            return value["result"]
    return {}


# --- build --------------------------------------------------------------

def split_label(value, default):
    """(label, path) from a `[LABEL=]path` --results/--log argument."""
    if "=" in value:
        label, _, path = value.partition("=")
        return label, path
    return default, value


def parse_build_args(argv):
    """(map, limit, verdict, delta, results_specs, log_specs), or
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
        lines.append("")
    return "\n".join(lines)


DELTA_TRUNCATED_NOTE = "\n\n(delta truncated; full delta in the run dir)\n"
DELTA_TRUNCATED_LINES = 200
DIFF_HEADER = re.compile(r'^diff --git ', re.MULTILINE)
DIFF_PLUS = re.compile(r'^\+(?!\+\+)', re.MULTILINE)
DIFF_MINUS = re.compile(r'^-(?!--)', re.MULTILINE)


def delta_summary(text):
    """"<n> files changed, +a/−b" derived from a git diff's own text."""
    files = len(DIFF_HEADER.findall(text))
    plus = len(DIFF_PLUS.findall(text))
    minus = len(DIFF_MINUS.findall(text))
    return f"{files} files changed, +{plus}/−{minus}"


def build_body(verdict_text, delta, results_entries, log_entries):
    parts = [
        "## Verdict", "", verdict_text.rstrip("\n"), "",
        "## Artifact delta", "", "```diff", delta["text"].rstrip("\n"), "```", "",
        render_results(results_entries),
    ]
    for entry in log_entries:
        parts += [f"## Log — {entry['label']}", "", "```",
                 *entry["lines"], "```", ""]
    return "\n".join(parts)


def cap(verdict_text, delta, results_entries, log_entries, limit):
    """The assembled body within `limit`, or None if it cannot fit.

    Truncates log_entries, results_entries' log fields and delta["text"]
    in place."""
    while True:
        body = build_body(verdict_text, delta, results_entries, log_entries)
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
                    progressed = True
                    break
            if progressed:
                break
        if progressed:
            continue

        if not delta.get("truncated"):
            summary = delta_summary(delta["text"])
            truncated_lines = delta["text"].splitlines()[:DELTA_TRUNCATED_LINES]
            delta["text"] = (summary + "\n\n" + "\n".join(truncated_lines)
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
    except OSError as exc:
        return refuse(str(exc))

    try:
        verdict_text = redact(Path(verdict_path).read_text(encoding="utf-8"), rows)
        delta_text = redact(Path(delta_path).read_text(encoding="utf-8"), rows)
    except OSError as exc:
        return refuse(str(exc))
    delta = {"text": delta_text}

    results_entries = []
    for label, path in results_specs:
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            return refuse(str(exc))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return refuse(f"{path}: not valid JSON ({exc})")
        for info in result_dict(data).values():
            if info.get("log"):
                info["log"] = redact(info["log"], rows)
        results_entries.append({"label": label, "data": data})

    log_entries = []
    for label, path in log_specs:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            return refuse(str(exc))
        text = redact(text, rows)
        log_entries.append({"label": label or Path(path).name,
                            "lines": text.splitlines()})

    body = cap(verdict_text, delta, results_entries, log_entries, limit)
    if body is None:
        print("cannot fit within --limit even after truncating log sections, "
              "stripping results log fields, and truncating the delta",
              file=sys.stderr)
        return 1

    sys.stdout.write(body)
    return 0


# --- check ----------------------------------------------------------------

def cmd_check(argv):
    map_arg = None
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        if flag == "--map":
            if not rest:
                return refuse("--map takes a value")
            map_arg = rest.pop(0)
        else:
            return refuse(f"{flag!r} is not an option this reads")
    if map_arg is None:
        return refuse("--map is required")

    body = sys.stdin.read()

    if PRIVATE_KEY.search(body):
        print("private key material in body", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        init = subprocess.run(["git", "init", "-q", str(tmp_path)],
                              env=git_env(), capture_output=True, text=True)
        if init.returncode != 0:
            return refuse(f"git init failed in {tmp_path}: {init.stderr.strip()}")

        (tmp_path / "report-body.md").write_text(body, encoding="utf-8")
        add = subprocess.run(["git", "-C", str(tmp_path), "add", "report-body.md"],
                             env=git_env(), capture_output=True, text=True)
        if add.returncode != 0:
            return refuse(f"git add failed in {tmp_path}: {add.stderr.strip()}")

        local_dir = tmp_path / "local"
        local_dir.mkdir()
        (local_dir / "device-identity.md").symlink_to(Path(map_arg).resolve())

        scan = subprocess.run(
            [sys.executable, str(TOOLS / "scrub-identity.py"), "--check", str(tmp_path)],
            env=git_env(), capture_output=True, text=True)

    return 0 if scan.returncode == 0 else 1


# --- post -------------------------------------------------------------

def cmd_post(argv):
    flags = {"--sha": "sha", "--state": "state", "--description": "description",
            "--pr": "pr", "--body": "body"}
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

    missing = [k for k in ("sha", "state", "description") if opts[k] is None]
    if missing:
        return refuse("missing required: " + " ".join(f"--{m}" for m in missing))
    if opts["state"] not in STATES:
        return refuse(f"--state must be one of {', '.join(STATES)}")
    if bool(opts["pr"]) != bool(opts["body"]):
        return refuse("--pr and --body must be given together")

    description = opts["description"][:DESCRIPTION_MAX]

    target_url = None
    if opts["pr"]:
        comment = subprocess.run(
            ["gh", "pr", "comment", opts["pr"], "--body-file", opts["body"]],
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
