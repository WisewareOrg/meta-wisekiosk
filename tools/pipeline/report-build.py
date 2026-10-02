#!/usr/bin/env python3
"""Render one pipeline run's report body.

    report-build.py --verdict <file> --delta <file> [--results <file>]
                     [--log <path> ...]
        -- assemble the run's Markdown body on stdout

Each --log is a path already tailed by the caller; its label is the file's
own basename. Each test case's own log, embedded in --results, is tailed to
the last TAIL_LINES lines. rc 0 always prints a body; rc 2 on a bad argument
or a --verdict/--delta file that cannot be read.
"""
import argparse
import json
import sys
from pathlib import Path

TAIL_LINES = 200


def result_dict(data):
    """The case->status dict from oeqa's `{<result-id>: {configuration, result}}`
    shape, or {} if data is not shaped like that."""
    if not isinstance(data, dict):
        return {}
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


def render_logs(paths):
    parts = []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            text = f"(could not read {path}: {exc})"
        parts += [f"## Log — {Path(path).name}", "", "```", text.rstrip("\n"), "```", ""]
    return "\n".join(parts)


def build_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--delta", required=True)
    parser.add_argument("--results")
    parser.add_argument("--log", action="append", default=[], dest="logs", metavar="PATH")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:])

    try:
        verdict = Path(args.verdict).read_text(encoding="utf-8").rstrip("\n")
        delta = Path(args.delta).read_text(encoding="utf-8").rstrip("\n")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"could not tell: {exc}", file=sys.stderr)
        return 2

    parts = ["## Verdict", "", verdict, "", "## Artifact delta", "",
             "```diff", delta, "```", ""]
    if args.results:
        parts.append(render_results(args.results))
    if args.logs:
        parts.append(render_logs(args.logs))

    sys.stdout.write("\n".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
