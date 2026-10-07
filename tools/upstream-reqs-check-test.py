#!/usr/bin/env python3
"""Self-test for tools/upstream-reqs-check.py's citation comparison.

    upstream-reqs-check-test.py        -- every case

A local item realising an upstream one cites it in its own `rationale`: a
line reads `<repo> <item id> <exact header>` (the ticket's own worked
example: "WiseKiosk SRS026 The display says when the backend is gone"). The
upstream `reviewed:` stamp is never embedded in that text -- it is recorded
in a separate local attribute on the citing item. Three functions here are
pure and are exercised with constructed values only: `read_srcrev` parses
`wisekiosk-src.inc`'s own text; `parse_citation` reads every citation line
out of a `rationale` string; `compare` is the predicate the module runs per
citation, against the citing item's own recorded stamp and one live-fetched
upstream item (or None, when the cited id wasn't found). None of the three
performs I/O -- the module's own `gh api` fetch, and the directory walk that
finds which local items cite what, run exclusively in the real, networked
pass `just verify` makes, never here.
"""
import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


upstream_reqs_check = load("upstream-reqs-check")

PASS, FAIL = [], []


def case(name, got, want):
    (PASS if got == want else FAIL).append(name)
    if got != want:
        print(f"FAIL  {name}\n        want {want!r}\n        got  {got!r}")


# Fabricated citation and stamp -- never a real item's rationale or a real
# upstream hash. The header and stamp are invented strings shaped like
# Doorstop's own (a short sentence, a base64-looking fingerprint), never
# copied from a real item.
MATCHING_HEADER = "A fixture needs no stock photo"
MATCHING_REVIEWED = "ZmFrZS1yZXZpZXdlZC1zdGFtcC0w="


def citation_line(repo="WiseKiosk", item_id="SRS901", header=MATCHING_HEADER):
    return f"{repo} {item_id} {header}"


# --- read_srcrev -----------------------------------------------------------
#
# A fixture .inc text, never the real wisekiosk-src.inc or its real pinned
# commit. SRC_URI sits directly above SRCREV and shares the "SRC" prefix on
# purpose -- a parser keyed on a loose "SRC.*=" match would read SRC_URI's
# own quoted value instead of SRCREV's.
INC_TEXT = (
    "# A fixture comment line, shaped like the real file's own.\n"
    "\n"
    'HOMEPAGE = "https://example.invalid/fixture/repo"\n'
    'LICENSE = "MIT"\n'
    "\n"
    'SRC_URI = "git://example.invalid/fixture/repo.git;protocol=https;branch=main"\n'
    'SRCREV = "0123456789abcdef0123456789abcdef01234567"\n'
    "\n"
    'PV = "0.0+git"\n'
)


def read_srcrev_cases():
    case("read_srcrev: reads SRCREV's value, not SRC_URI's",
         upstream_reqs_check.read_srcrev(INC_TEXT),
         "0123456789abcdef0123456789abcdef01234567")


# --- parse_citation ---------------------------------------------------------

def parse_citation_cases():
    case("parse_citation: an empty rationale cites nothing",
         upstream_reqs_check.parse_citation(""), [])

    case("parse_citation: a rationale with no item-id-shaped line cites nothing",
         upstream_reqs_check.parse_citation(
             "Written for this item alone, no upstream need.\n"),
         [])

    case("parse_citation: a repo and item id with no header text is not a citation",
         upstream_reqs_check.parse_citation("WiseKiosk SRS901\n"), [])

    case("parse_citation: one citation line returns one tuple",
         upstream_reqs_check.parse_citation(citation_line() + "\n"),
         [("WiseKiosk", "SRS901", MATCHING_HEADER)])

    two_citations = (
        citation_line(item_id="SRS901", header="First cited need") + "\n"
        "Some connecting prose that cites nothing itself.\n"
        + citation_line(item_id="SRS902", header="Second cited need") + "\n"
    )
    case("parse_citation: two citation lines in one rationale return two tuples",
         upstream_reqs_check.parse_citation(two_citations),
         [("WiseKiosk", "SRS901", "First cited need"),
          ("WiseKiosk", "SRS902", "Second cited need")])


# --- compare -----------------------------------------------------------------

def compare_cases():
    case("compare: a matching header and a matching reviewed stamp passes",
         upstream_reqs_check.compare(
             MATCHING_HEADER, MATCHING_REVIEWED,
             {"header": MATCHING_HEADER, "reviewed": MATCHING_REVIEWED}),
         [])

    mismatched_header = upstream_reqs_check.compare(
        MATCHING_HEADER, MATCHING_REVIEWED,
        {"header": "A different header entirely", "reviewed": MATCHING_REVIEWED})
    case("compare: a header that no longer matches upstream fails",
         mismatched_header != [], True)
    case("compare: that failure names the header as what differs",
         any("header" in m.lower() for m in mismatched_header), True)

    stale_reviewed = upstream_reqs_check.compare(
        MATCHING_HEADER, "a-stamp-this-item-was-reviewed-against-long-ago",
        {"header": MATCHING_HEADER, "reviewed": MATCHING_REVIEWED})
    case("compare: a matching header but a local stamp stale against upstream's"
         " current reviewed value still fails", stale_reviewed != [], True)
    case("compare: that failure names reviewed as what differs",
         any("reviewed" in m.lower() for m in stale_reviewed), True)

    missing_upstream = upstream_reqs_check.compare(MATCHING_HEADER, MATCHING_REVIEWED, None)
    case("compare: a cited item absent from the fetched upstream set fails",
         missing_upstream != [], True)
    case("compare: that failure says the item was not found",
         any("not found" in m.lower() for m in missing_upstream), True)


def main() -> int:
    read_srcrev_cases()
    parse_citation_cases()
    compare_cases()
    print(f"\npass={len(PASS)} fail={len(FAIL)} skip=0")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
