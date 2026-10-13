# Requirements

Three Doorstop documents trace this image's own obligations: `sys/` (`SYS` — what the kiosk's two
stakeholders need: the viewer at the panel, and the maintainer, who is never at the panel and updates
and services the unit over the network), `srs/` (`SRS` — what the kiosk does to meet each need), and
`tst/` (`TST` — one verification each: a stimulus, an observation and a pass condition a person can
perform against the appliance and watch fail). Every item's `verification-justification` states what
its checks settle and what they leave unproven. A `TST` item's `references`, where it carries any, pin
each file by hash, and the gate fails an item whose referenced file changed after review. The
pipeline's tier guarantees stay in [`../testing.md`](../testing.md); this tree holds the image's own
obligations.

**An item states a need — what the viewer or the maintainer needs — never a mechanism.** A rendering
setting, a render node held by a process, a flag on a unit file, a probe channel: those are mechanisms
that deliver a need. They live in the launcher, the recipes and `docs/testing.md`, are recorded as
context in the run record, and this tree never asserts them.

The gate — [`wise-ci`](https://github.com/WisewareOrg/wise-ci)'s shared `check-reqs`, pinned in
`pyproject.toml`/`uv.lock` — is guard 21 of [`tools/ci-guards.sh`](../../tools/ci-guards.sh), so
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

**A placeholder with no bound sits `active: false` too.** Its check cannot fail while no bound is
stated, and its `rationale` says so; it is activated in the pull request that states the bound. An
active `SRS` whose only `TST` children are placeholders is unverified, and its
`verification-justification` says so: Doorstop counts an inactive child's link as coverage, so the
gate does not flag it.
