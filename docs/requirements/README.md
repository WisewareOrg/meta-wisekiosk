# Requirements

Three Doorstop documents trace this image's own obligations: `sys/` (`SYS` — what the kiosk needs to
do, as a person at the panel would state it), `srs/` (`SRS` — the obligations the checks in
`docs/testing.md`'s tiers discharge), and `tst/` (`TST` — one verification item per obligation,
referencing its case file by keyword with a hash pin on the file). The pipeline's tier guarantees stay in
[`../testing.md`](../testing.md); this tree holds the image's own obligations.

**An item states a need — what a person at the panel needs here — never a mechanism.** A rendering
setting, a render node held by a process, a flag on a unit file, a probe channel: those are mechanisms
that deliver a need. They live in the launcher, the recipes and `docs/testing.md`, are recorded as
context in the run record, and this tree never asserts them.

The gate — [`wise-ci`](https://github.com/WisewareOrg/wise-ci)'s shared `check-reqs`, pinned in
`pyproject.toml`/`uv.lock` — is guard 23 of [`tools/ci-guards.sh`](../../tools/ci-guards.sh), so
`just guards`, the pre-commit hook and the CI `guards` job run it; it reviews the whole tree, not a
diff, so every run checks every item.

The tree holds the appliance's own needs. The application's requirements stay in the application's
own tree; no item here realises, cites or tracks one of them.

Acceptance runs for a `TST` item live in gitignored `local/`, never under this tree, and are cited
from the pull request that lands the case.

**An item awaiting its own decomposition sits `active: false`** — the same idiom `check-reqs`
already documents for a `TST` item with no verification yet, applied one tier up for a `SYS`/`SRS`
item whose children are a later step's scope. It is reactivated in the pull request that adds those
children, never left inactive once they exist.

