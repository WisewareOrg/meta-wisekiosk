# Requirements

Three Doorstop documents trace this image's own obligations: `sys/` (`SYS` — what the kiosk needs to
do, as a person at the panel would state it), `srs/` (`SRS` — the obligations the checks in
`docs/testing.md`'s tiers discharge), and `tst/` (`TST` — one verification item per obligation,
referencing its case file by keyword with a hash pin on the file). Why this tree exists at all, over
the obligation statement `docs/testing.md` already carries for the pipeline, is
[`../decisions/0001-verification-architecture.md`](../decisions/0001-verification-architecture.md).

**An item states a need — what a person at the panel needs here — never a mechanism.** A rendering
setting, a render node held by a process, a flag on a unit file, a probe channel: those are mechanisms
that deliver a need. They live in the launcher, the recipes and `docs/testing.md`, are recorded as
context in the run record, and this tree never asserts them.

The gate — [`wise-ci`](https://github.com/WisewareOrg/wise-ci)'s shared `check-reqs`, pinned in
`pyproject.toml`/`uv.lock` — runs through [`tools/check-reqs.sh`](../../tools/check-reqs.sh), called
from `just verify`, `just guards`, and the CI `guards` job; it reviews the whole tree, not a diff, so
every run checks every item. [`tools/upstream-reqs-check.py`](../../tools/upstream-reqs-check.py)
checks, in the same two surfaces, that a local item citing a WiseKiosk obligation still matches it at
the pinned `SRCREV`.

Acceptance runs for a `TST` item live in gitignored `local/`, never under this tree, and are cited
from the pull request that lands the case.

**An item awaiting its own decomposition sits `active: false`** — the same idiom `check-reqs`
already documents for a `TST` item with no verification yet, applied one tier up for a `SYS`/`SRS`
item whose children are a later step's scope. It is reactivated in the pull request that adds those
children, never left inactive once they exist.

**A local item realising an upstream WiseKiosk obligation cites it in its own `rationale`**: the
first line reads `<repo> <item id> <exact header>` (e.g. `WiseKiosk SRS026 The display says when the
backend is gone`). The upstream `reviewed:` stamp it was reviewed against is recorded separately, in
the citing item's own `upstream-reviewed` attribute — never embedded in the `rationale` text.
Whichever tier first carries a citing item must add `upstream-reviewed` to that tier's
`.doorstop.yml` under `attributes.reviewed:`, the same place `rationale` and the two
`verification-*` attributes already sit: leaving it out would let the recorded stamp be edited
without Doorstop ever treating the item as unreviewed, defeating the re-review
[`tools/upstream-reqs-check.py`](../../tools/upstream-reqs-check.py) exists to force.
