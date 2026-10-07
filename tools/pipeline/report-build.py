#!/usr/bin/env python3
"""Render one pipeline run's report body.

    report-build.py --verdict <file> [--results <file>]
                     [--log <path> ...]
        -- assemble the run's Markdown body on stdout

Each --log is a path already tailed by the caller; its label is the file's
own basename. Each test case's own log, embedded in --results, is tailed to
the last TAIL_LINES lines. rc 0 always prints a body; rc 2 on a bad argument
or a --verdict file that cannot be read.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "meta-wisekiosk" / "lib"))
from oeqa.runtime.cases.kiosk import record as _record  # noqa: E402

TAIL_LINES = 200

# The order the record's lines render in -- tool, board, image, app, sut,
# then every probe case's own page.<case id> line, sorted. The key itself
# is _record.RECORD_KEY, imported, never a second spelling.
RECORD_ORDER = ("tool", "board", "image", "app", "sut")


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


def render_record(record):
    """The run record's own lines, verbatim and in order, under one
    heading. Interprets none of them: a key this function does not name
    still renders, after the named ones, sorted."""
    page_keys = sorted(k for k in record if k.startswith("page."))
    named = list(RECORD_ORDER) + page_keys
    unknown = sorted(k for k in record if k not in named)
    lines = [str(record[key]) for key in named + unknown if key in record]
    return "\n".join(["## Run record", "", "```", *lines, "```", ""])


def render_results(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "## Test results\n\n(could not read the results file)\n"
    cases = result_dict(data)
    record = cases.pop(_record.RECORD_KEY, None)
    parts = [render_record(record)] if record else []
    if not cases:
        parts.append("## Test results\n\n(no cases in the results file)\n")
        return "\n".join(parts)
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
    parts.append("\n".join(lines))
    return "\n".join(parts)


def render_logs(paths):
    parts = []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            text = f"(could not read {path}: {exc})"
        parts += [f"## Log — {Path(path).name}", "", "```", text.rstrip("\n"), "```", ""]
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--results")
    parser.add_argument("--log", action="append", default=[], dest="logs", metavar="PATH")
    args = parser.parse_args(sys.argv[1:])

    try:
        verdict = Path(args.verdict).read_text(encoding="utf-8").rstrip("\n")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"could not tell: {exc}", file=sys.stderr)
        return 2

    parts = ["## Verdict", "", verdict, ""]
    if args.results:
        parts.append(render_results(args.results))
    if args.logs:
        parts.append(render_logs(args.logs))

    sys.stdout.write("\n".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
