# 0001 — Trace the image's own obligations with a lean, shared Doorstop tree

**Status:** accepted
**Decided:** 2026-10-06
**Rev:** 1

## Revisions

- **rev 1** — 2026-10-06 — first written (#204 the requirements tree, part of #202 Verification
  architecture).

## Context

Nothing in this repository named the image's own obligations and linked each to the check that
discharges it. `docs/testing.md` states what each test tier guarantees, decided 2026-09-30 as the
obligation statement for the pipeline — but a tier's guarantee is a sentence about a harness, not an
identifiable need a reviewer can cite, link a check to, or watch grow check by check as the kiosk's
own behaviour is decomposed.

WiseKiosk already carries exactly this: a Doorstop tree of `SYS`/`SRS`/`TST` items, and a shared gate
(`check-reqs`) enforcing review discipline, verification-method consistency and reference freshness
across it. Building a second, independent implementation of that gate here — rather than consuming
the one WiseKiosk already has — would be the thing consolidate-don't-propagate exists to prevent.

## Decision

A Doorstop tree under `docs/requirements/` traces this image's own obligations — not the pipeline's,
which `docs/testing.md` continues to own. It is extremely lean: it grows only as a check lands, never
ahead of one, and every item states a need a person at the panel has, never a mechanism a check
happens to use.

The tree mirrors WiseKiosk's own exactly where there is no reason to differ: the same `SYS`/`SRS`/
`TST` prefixes, so a bare ID is unambiguous within a repository and every cross-repository citation
names the repository explicitly; and the same gate, `check-reqs`, migrated out of WiseKiosk into
`wise-ci` so both repositories consume one implementation, each pinned by commit with its own Doorstop
pin riding in on it — never a second copy of either script or pin. A one-line validator shim in this
repository's `tst/` document imports the shared validator.

The verification library this tree's `TST` items point at is laid out per evaluator —
`meta-wisekiosk/lib/wisekiosk/<evaluator>/`, with that evaluator's own constructed-input tests
alongside it — and a `TST` item references its case file by keyword, with the case file's whole-file
hash recorded so a changed case un-reviews the item that cites it. No `docs/requirements/evidence/`
tree exists; acceptance runs stay in gitignored `local/` and are cited from the PR that lands the
case, never from the tree itself.

A rendering setting, a render node held by a process, a flag on a unit file, a probe channel: these
are mechanisms that deliver a need, not needs themselves, and the tree never asserts them. This is
why a later step retires `tools/kiosk-gpu-check.sh` outright, with no successor item, rather than
this one: the user need it stood near — the display is on the screen, laid out right, painting,
smooth — is already owned by the applied, layout, render and performance obligations, and the
setting it checked is recorded as run-record context instead.

Each step of this effort lands as one pull request into one integration branch named for the parent
ticket, proven whole on bench before that branch lands on `main` as a single pull request closing the
ticket — rather than a stack of sibling pull requests landing independently on `main`, which would let
a later step's obligations and checks drift out of order with the ones before it.

## Alternatives considered

**Keep `docs/testing.md` as the sole obligation statement for the image, as the 2026-09-30 decision
set for the pipeline.** Rejected for the image's own obligations: a tier guarantee is not an
identifiable, linkable unit, and growing it item by item as a check lands has no natural home in
prose the way it does in a tree built for exactly that.

**Build a second `check-reqs` implementation local to this repository.** Rejected: WiseKiosk's gate
already exists, is already proven, and a second implementation is the fact restated in two places that
consolidate-don't-propagate exists to prevent. Consuming the shared package pinned by commit, with no
second Doorstop pin, is strictly less to maintain.

**Keep `tools/kiosk-gpu-check.sh` as a standing case.** Rejected: it asserted a rendering setting, a
mechanism, and passed by accident under the architecture later chosen; the need it stood near was
already owned elsewhere in the tree this decision establishes.

**Land each step's pull request independently on `main`.** Rejected: a later step's items and checks
would be reviewed and merged against a `main` that does not yet carry the step before it, risking a
tree that briefly asserts an obligation no landed check discharges, or two steps disagreeing on a
shape neither has seen the other's PR resolve.

## Consequences

Every obligation this image carries now has a stable, citable identifier, and a reviewer can see
directly which check discharges which need — and which needs nothing discharges yet. A citation
crossing into WiseKiosk's own tree is gated against drift: `tools/upstream-reqs-check.py` fails when a
locally-cited upstream item's header or review stamp no longer matches what was recorded at citation
time, naming the item and what changed.

This makes adding a new check slightly more ceremonious: a check landing with no backing `TST` item
(and, where applicable, `SRS`/`SYS` ancestry) is now visibly incomplete rather than merely
undocumented. It forecloses a second, independently-maintained Doorstop pin or gate implementation in
this repository, and forecloses landing a step's obligations on `main` ahead of the step before it.
