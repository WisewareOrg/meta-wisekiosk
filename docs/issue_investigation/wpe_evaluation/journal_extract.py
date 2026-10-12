#!/usr/bin/env python3
"""The last payload a single-line parser accepts, out of a journal or capture's lines.

Contract: journal_extract_test.py's header.
"""


def last_parseable(lines, parse_fn):
    """parse_fn's result for the last line it parses, or None."""
    last = None
    for line in lines:
        d = parse_fn(line)
        if d is not None:
            last = d
    return last
