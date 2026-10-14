# Requirements

Three Doorstop documents trace this image's own obligations: `sys/` (`SYS` — what the kiosk's two
stakeholders need: the viewer at the panel, and the operator, who configures, deploys and maintains
the unit; a unit can have more than one operator, and whoever signs its updates is one of them),
`srs/` (`SRS` — what the kiosk does to meet each need), and `tst/` (`TST` — one verification each: a
stimulus, an observation and a pass condition, checked automatically against the appliance). Every
item's `verification-justification` argues why it is verified the way it is. Its `rationale` says
why the item was written: what goes wrong for the viewer or the operator if the need is not met. It
does not restate the item's text or describe its check, and it never names a test; the item's
references do that. A `TST` item's `references`, where it carries any, pin each file by hash, and
the gate fails an item whose referenced file changed after review. The testing tiers' own guarantees
stay in [`../testing.md`](../testing.md); this tree holds the image's own obligations.

**Every `SYS` item traces to a goal in [`../../README.md`](../../README.md) §"Mission".**

**An image update and a configuration change are different things, and no item says "update"
alone.** An image update replaces the image the appliance runs; a configuration change alters the
configuration it holds.

**An item states a need — what the viewer or the operator needs — never a mechanism.** A rendering
setting, a render node held by a process, a flag on a unit file, a probe channel: those are
mechanisms that deliver a need. They live in the launcher, the recipes and `docs/testing.md`, are
recorded as context in the run record, and this tree never asserts them.

The gate — [`wise-ci`](https://github.com/WisewareOrg/wise-ci)'s shared `check-reqs`, pinned by
commit in `.github/workflows/guards.yml` for the CI `guards` job and in `pyproject.toml`/`uv.lock`
for `just reqs`, which runs it locally on demand — it reviews the whole tree, not a diff, so every
run checks every item.

The tree holds the appliance's own needs. The application's requirements stay in the application's
own tree; no item here realises, cites or tracks one of them.

Acceptance runs for a `TST` item live in gitignored `local/`, never under this tree, and are cited
from the pull request that lands the case.

**An item awaiting its own decomposition sits `active: false`** — the same idiom `check-reqs`
already documents for a `TST` item with no verification yet, applied one tier up for a `SYS`/`SRS`
item whose children are a later step's scope. It is reactivated in the pull request that adds those
children, never left inactive once they exist.

**An `SRS` states a required capability, a performance need, or the appliance's response to a fault
it can credibly suffer.** A required capability is one the appliance could lose, such as to a
hardening change, and its `TST` checks that it is still there. A fault response is one failure as
the viewer or the operator sees it: the appliance detects it and recovers what that person needs.
Each way of inducing that failure is a `TST` under it, which injects the fault and observes the
response, so a newly found way becomes another `TST`, not another `SRS`. A fault is credible once it
has been seen or the design makes it certain, and a newly found one becomes a new item whose
response is designed against it.

**A performance number is stated in the `TST` item that checks it**, never in a `SYS` or `SRS`
item, so tuning it is a change to that check and not to the need it verifies.

**Every `TST` item is an automated check, and it sits `active: false` until that check is written
against it** — the pending-verification convention of the [WiseKiosk
tree](https://github.com/WisewareOrg/WiseKiosk/blob/main/docs/requirements/README.md). A pending
item's header starts `Pending:`, and its `rationale`, after saying why the item exists, also says
what it waits on: its test, its bound, or hardware the project lacks. The change that lands its
test activates it, re-reads it in full and stamps its review. An active `SRS` whose `TST` children
are all pending is unverified: Doorstop counts an inactive child's link as coverage, so the gate
does not flag it, and the `Pending:` headers beneath it are what say so.
