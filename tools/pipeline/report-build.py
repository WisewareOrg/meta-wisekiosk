#!/usr/bin/env python3
"""Render one pipeline run's report body.

    report-build.py --verdict <file> --delta <file> [--results <file>]
                     [--log <label>=<file> ...]
        -- assemble the run's Markdown body on stdout

Each --log is tailed to the last TAIL_LINES lines; the whole body is capped
at TOTAL_LIMIT characters. rc 0 always prints a body; rc 2 on a bad argument
or a --verdict/--delta file that cannot be read.
"""
import json
import sys
from pathlib import Path

TAIL_LINES = 200
TOTAL_LIMIT = 60000


def refuse(reason):
    print(f"could not tell: {reason}", file=sys.stderr)
    return 2


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


def tail(text, n=TAIL_LINES):
    lines = text.splitlines()
    if len(lines) <= n:
        return text.rstrip("\n"), False
    return "\n".join(lines[-n:]), True


def render_results(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "## Test results\n\n(could not read the results file)\n"
    cases = result_dict(data)
    if not cases:
        return "## Test results\n\n(no cases in the results file)\n"
    lines = ["## Test results", "", "| case | status |", "|---|---|"]
    for case_id in sorted(cases):
        lines.append(f"| {case_id} | {cases[case_id].get('status', '?')} |")
    lines.append("")
    for case_id in sorted(cases):
        info = cases[case_id]
        log = info.get("log")
        if info.get("status") == "PASSED" or not log:
            continue
        body, truncated = tail(log)
        lines += [f"### {case_id}", "", "```", body, "```"]
        if truncated:
            lines.append(f"(tailed to the last {TAIL_LINES} lines)")
        lines.append("")
    return "\n".join(lines)


def render_logs(log_specs):
    parts = []
    for label, path in log_specs:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            text = f"(could not read {path}: {exc})"
        body, truncated = tail(text)
        parts += [f"## Log — {label}", "", "```", body, "```"]
        if truncated:
            parts.append(f"(tailed to the last {TAIL_LINES} lines)")
        parts.append("")
    return "\n".join(parts)


def parse_args(argv):
    opts = {"verdict": None, "delta": None, "results": None}
    logs = []
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        if flag in ("--verdict", "--delta", "--results"):
            if not rest:
                return None, f"{flag} takes a value"
            opts[flag[2:]] = rest.pop(0)
        elif flag == "--log":
            if not rest:
                return None, "--log takes a value"
            value = rest.pop(0)
            if "=" not in value:
                return None, "--log takes label=path"
            label, _, path = value.partition("=")
            logs.append((label, path))
        else:
            return None, f"{flag!r} is not an option this reads"
    if opts["verdict"] is None or opts["delta"] is None:
        return None, "missing required: --verdict --delta"
    return (opts, logs), None


def main():
    argv = sys.argv[1:]
    if argv == ["--help"]:
        print(__doc__.strip())
        return 0
    parsed, why = parse_args(argv)
    if why:
        return refuse(why)
    opts, logs = parsed

    try:
        verdict = Path(opts["verdict"]).read_text(encoding="utf-8").rstrip("\n")
        delta = Path(opts["delta"]).read_text(encoding="utf-8").rstrip("\n")
    except (OSError, UnicodeDecodeError) as exc:
        return refuse(str(exc))

    parts = ["## Verdict", "", verdict, "", "## Artifact delta", "",
             "```diff", delta, "```", ""]
    if opts["results"]:
        parts.append(render_results(opts["results"]))
    if logs:
        parts.append(render_logs(logs))

    body = "\n".join(parts)
    if len(body) > TOTAL_LIMIT:
        body = body[:TOTAL_LIMIT] + "\n\n(report truncated; full report in the run dir)\n"

    sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
