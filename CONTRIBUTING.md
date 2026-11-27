# Contributing to meta-wisekiosk

How to run the checks, what the conventions are, and how a change gets merged. What this repository
is, and the index of its documents, is the [README](README.md); the rules an AI agent works under are
[`CLAUDE.md`](CLAUDE.md). The organisation's own process — branch names, ticket types, milestones,
pull-request titles, each with the gate that enforces it — is WisewareOrg's
[`PROCESS.md`](https://github.com/WisewareOrg/.github/blob/main/PROCESS.md), and applies here in full.

**This repository is public.** No device address, hostname, SSID, PSK hash, MAC, serial or machine-id
belongs in a tracked file — not in a doc, not in a test fixture, not in a comment. None of it is
credential-shaped, so no secret scanner stops it, and together it fingerprints one network. The real
values live in gitignored `local/device-identity.md` and in `~/.config/wisekiosk/secrets.yaml`; the
tree names no board by address, and finds one at use time with `just find <cidr>`.

## Before you change anything

**Build with `just build`, never `kas-container` directly** — the build inputs it writes first are
[`docs/image.md`](docs/image.md) §"Building".

**Decide a WebKit rebuild before starting it.** Which changes rebuild WebKit, and which rebuild more,
is [`docs/image.md`](docs/image.md) §"What a rebuild costs".

**Test on the bench board.** Every test on a board runs through the bench runner,
[`docs/testing.md`](docs/testing.md) §"Running it".

**Nothing autogenerable is committed.** A file this tree can regenerate from what is already pinned
is gitignored and written at build entry instead of checked in: `meta-wisekiosk/conf/build-rev.inc`,
`wisekiosk-backend-go-mods.inc` and `wisekiosk-frontend/npm-shrinkwrap.json`, by
`tools/write-build-rev.sh`, `tools/go-mods.py` and `tools/app-lockfile.py`. Bumping the WiseKiosk
app pin is therefore a one-line `SRCREV` edit
([`meta-wisekiosk/recipes-wisekiosk/wisekiosk/README.md`](meta-wisekiosk/recipes-wisekiosk/wisekiosk/README.md)).
A pin on the repository's own tooling is the opposite case: `pyproject.toml` and `uv.lock` fix the
versions of what `tools/*.py` and the tests import, as `includes/base.yaml` fixes a layer commit, and
a pin is never autogenerable, so it belongs in the tree.

## Running the checks

```sh
just                # the recipe roster, each beside what it does
just verify         # every documentation check: cross-references + docs-vs-image
just links          # cross-references only
just guards         # repository invariants: secrets, identity, syntax, wiring;
                    # runs the self-tests of the device guard, the CVE tools and the host-side tools too
just reqs           # the requirements tree, through wise-ci's check-reqs
just adrs           # docs/decisions/ and every ADR citation, through wise-ci's check-adrs
just install-hooks  # once per clone: point core.hooksPath at .githooks
bash .claude/hooks/guard-test.sh   # the device guard's self-test on its own
```

The pre-commit hook runs [`tools/ci-guards.sh`](tools/ci-guards.sh),
[`tools/doc-links.py`](tools/doc-links.py) and [`tools/scrub-identity.py`](tools/scrub-identity.py)
`--check`. CI runs the same three in its `guards` workflow, so a commit cannot pass locally and fail
there on them, plus wise-ci's `check-reqs` over the requirements tree
([`docs/requirements/README.md`](docs/requirements/README.md)) and `check-adrs` over
[`docs/decisions/`](docs/decisions/README.md) and every ADR citation. The `lint` workflow runs
shellcheck over every tracked shell script and actionlint over the workflows, and `codeql` analyses
the tooling. `just image` and `just verify`'s second half need a populated `build/` and are
local-only: CI never builds.

`tools/scrub-identity.py --check` has two halves and says which ran. The pattern half needs no
configuration and runs everywhere. The known-value half reads `local/device-identity.md`, which is
gitignored and therefore absent in CI — so a run there reports PARTIAL, never "clean". A hostname or
an SSID has no recognisable shape; only the map can catch one, and only where the map exists.

**A PARTIAL scan exits 1.** A run that could not perform half its search must not return the code
for "nothing found", so the absence of the map is a finding wherever the map could exist. The one
caller that structurally cannot hold it — CI, which clones without `local/` — passes
`--allow-partial` and carries the reason in its own step. On a checkout with no map the pre-commit
hook and `just guards` therefore fail where CI passes: create `local/device-identity.md`, or pass
`--allow-partial` yourself and know that a hostname or an SSID went unlooked-for.

None of the above builds or boots anything — [`docs/testing.md`](docs/testing.md) covers the tiers
that do, what each one proves, and how the bench runner runs them.

## Documentation conventions

**Colocation, and one owner per fact.** Documentation lives beside the code it explains — a recipe's
README is as much documentation as anything under `docs/`. State a fact in the document that owns it
and cite it from everywhere else; the index in [`README.md`](README.md) §"Documentation" says which
document answers which question. A second independent statement goes stale in one copy while the
other stays right, with nothing comparing them.

**Three layers of document.** Each module of the layer has a README: what it puts on the image, how
it plugs into the rest, and the knobs that matter, in plain language — Yocto is hard to read. A
subsystem document under `docs/` says how the modules fit together and why the system is built that
way, and links down to the module READMEs. A decision record in [`docs/decisions/`](docs/decisions/README.md)
holds a choice that took a trade study, with the alternatives it rejected. No document states what a
board runs, which slot it is on, or what may be done to it.

**The tree describes the system; issues and pull requests are the record of the work.** A recipe, a
class or a justfile says what the tree does today, and a document says how the system is built and
why. How a problem was traced to its cause and fixed stays on its issue and pull request; a design
choice, with the alternatives it rejected and why, goes in its ADR
([`docs/decisions/`](docs/decisions/README.md)). Neither goes in a comment or a "no longer" clause.
State the timeless fact — no *now*, *no longer*, *as of*.

**Cite a section by name, never by line number.** A section reference is a Markdown link to the
file, then `§`, then the heading in double quotes — as [`docs/image.md`](docs/image.md) §"Building" is
cited above. [`tools/doc-links.py`](tools/doc-links.py) gates that form against the real headings,
and it cannot see a line number rot. Show the form by citing a real section, as here: the checker
reads Markdown link syntax anywhere on a line, backticks included, so an invented filename written
as an illustration is a broken link like any other. The same rule holds for anything
renumberable — write `issue #46 build stamp`, number *and* name, because a renumber rewrites links
and leaves prose untouched. Ordinal references in prose ("step 3") are reported as warnings for exactly
this reason.

**Links are hub-and-spoke.** A new document gets a row in [`README.md`](README.md) §"Documentation";
relative links resolve from the citing file's own directory, and a leading `/` fails. Never anchor a
*directory* link — anchor its `README.md`.

## Writing a target-suite test

**A test's contract is its item's text.** Each target-suite test checks one `TST` item in
[`docs/requirements/tst/`](docs/requirements/tst/): the stimulus it states, its bound, and its pass, fail
and invalid conditions. Nothing else is part of the contract. A test records `requirement`, the
values its item judges, under the same names as every test of its kind (a recovery records
`back_s`), and what tells its case or its stimulus apart, or explains a failure the judged values
cannot. A check the item does not ask for is not in the test.

**Every test reads arrange, act, assert,** three blocks separated by single blank lines, against
`self.board` and `self.record`. A test method takes only `self` and its parametrized values: before
each test, the autouse `_board_and_record` in `tests/target_suite/conftest.py` puts a new `Board`
and the test's `Record` on the instance. That Board is built with the test's fixture lookup, and
reaches what the run builds on demand through `board.fixture(name)` — the update bundles as
`board.updates.bundles`, the refused offers as `board.updates.refused_offers`, the start-of-run
install as `board.updates.installed`, the evemu build, and the replay proxy that
`@replaying(<recording>)` (`board_test.py`) puts on a test. A board a fixture opens for itself has
no fixture lookup, and `board.fixture` says so. A class holds test methods and, when every test in
it starts from the same board state, a `setup_method`; no class writes `teardown_method`, which
would run after the board's undo. A test whose stimulus must be judged taken before its outcome can
be timed adds one act and assert pair, as TST006<!-- Image update with a new application build -->
judges the update installed and restarted into before it times the panel from that restart. So does
a test with a second stimulus: TST023<!-- Image that cannot start --> and
TST024<!-- Image that cannot reach the network --> judge the fallback before they install a
valid update. So does a test whose second read can be invalid where the first can already show a
breach: TST005<!-- Frozen page recovered --> judges its time before it reads the picture, so that an
invalid read does not hide a late panel.

**Tests that differ only in stimulus and bound are one parametrized test.** Each row is
`case(<TST id>, <values>…)`, which makes the item's id the case's id and its first value. A
fault-to-back test's row is the item, its fault, the read that says the thing is back, and its
bound: the fault returns the host instant its time counts from, mapped from the board's own record
where only the board knows it, and `board.seconds_until(<read>, since=…)` times from it. Instants are
the host's `time.monotonic()`, taken on the side of the event that can only overstate a time.

**A stimulus that did not take fails the check as invalid, from inside the stimulus.** A method that
applies a stimulus confirms it took and raises through `invalid_if(<how it did not take>)`
(`tests/board/part.py`), so the message reads `INVALID CHECK, not an appliance failure: …` and the
test body holds no validity logic of its own. Where the stimulus was applied and only its strength
or the board's starting state is in doubt, a `confirm_…` call ends the assert block instead, so an
observed breach fails first: TST008<!-- Sustained network load -->'s load, and the configuration
tests' loss check. A stimulus that did not take is judged invalid from inside it, before its outcome
is read, and so is one whose invalid condition can itself cause the breach, as a page reload makes
frame stalls. A breach the stimulus itself reveals fails the test from inside it, as an assertion that
is not marked invalid: `Board.restart_with` fails a board that does not come back in a new boot,
which is TST004<!-- Kernel crash -->'s restart by itself, and `Network.cut_off` fails a board that
restarted during the outage. A starting state that makes the stimulus impossible to apply is
confirmed before it instead: TST008<!-- Sustained network load -->'s link, read by
`Network.confirm_link_carries_load`, stops the call as invalid before any load when the board's own
send rate is at or below the floor TST008<!-- Sustained network load --> states (`LINK_FLOOR_MBIT`),
a sign of the link, not the rate the load travels at.

**A test holds what it measured before the stimulus,** in a name that says so, and compares the
after against it.

**The board is a tree of parts** (`tests/board/`). `Board` itself is the connection, the restarts,
the faults on the whole board, the waits, and the way to a run's fixtures; everything else belongs to
a part, a subclass of `Part` that `Board.__init__` builds. Their class docstrings say what each one
holds. A part registers its undos on `board.cleanup` and reaches a sibling only through the board's
public path (ruff's SLF001 gates that). A part never holds the record: every method returns what it
measured, and the test records it. A recorded read returns its raw text, with the parse where a
record needs it. A named result type exists only where the value is passed whole, carries methods,
or has neighbouring fields of one type that a reorder could silently swap. `tests/board/` imports
nothing from `tests/target_suite/` at run time.

**Waits for a condition are tenacity polls,** in `Board.seconds_until`, `Board.wait_for` and
`Board.longest_lapse_s`, which take a read that raises one of `Board.ERRORS` as one that does not
hold, and fail the test once the wait gives up. A read a wait polls says "not yet" by returning
False or None, or by raising one of `Board.ERRORS`; an assertion inside it ends the wait at once,
which is right only where the read means it to. A wait whose caller needs what the read saw returns
it: `wait_for` returns the first read that has a value, so no part keeps a read aside for a later
caller.

**Teardown and record order.** For each test, in this order: the autouse fixtures run,
`_board_and_record` builds the Board and the Record, and `device_context` records the device facts;
`setup_method` runs; the test's own fixtures start; the test runs;
`pytest_runtest_teardown` (`tests/target_suite/conftest.py`) closes the Board's cleanup, last first,
while the fixtures are still alive; then the fixtures tear down, each recording what it holds as it
goes.

**Ordering and selection.** `@pytest.mark.sends_update` is the only ordering rule:
`pytest_collection_modifyitems` runs the marked tests after every other, and an install from a test
without the mark fails it. A case marked
`@pytest.mark.soak` is deselected unless the run passes `--soak`.

**The lint gate.** [`tools/ci-guards.sh`](tools/ci-guards.sh) runs the repo `.venv`'s
pinned `ruff check` (the select in `pyproject.toml`), `ruff format --check`, `interrogate --fail-under
100` and `pydoclint` over every tracked `tests/*.py`; a missing tool fails the guard.

## Tickets, branches and pull requests

Work on a branch and land through a pull request; nothing goes directly to `main`. A pull request
**closes its issue or stands as a self-complete deliverable**, and a change that does neither is not
ready to open, let alone to call merge-ready.

Issues block each other through GitHub's native dependency edges, never through a label. Write both
the number and the name of anything renumberable, in the title and in the body.

## Getting a change merged

Size a change by what can be **read in one sitting**. Keep the diff to intended files. Verify through
CI, not only a local run, and walk the checklist below against the diff.

**A gate is not verified until you have watched it fail.** Seed the defect *and* the
spelled-differently-but-valid variant, confirm the seed landed, and re-run the finding's own
reproduction against the fix. A check that looks identical passing and failing has measured nothing —
which is why `.claude/hooks/guard.sh` ships with `guard-test.sh` beside it, why the CVE and currency
tools ship with [`tools/cve-tools-test.py`](tools/cve-tools-test.py) beside them, and why every guard
in [`tools/ci-guards.sh`](tools/ci-guards.sh) existence-checks the paths it scans before scanning
them.

## Review checklist

Each question is an obligation on the author that leaves no artifact, so no check decides it — the
reviewer is the mechanism. `.claude/hooks/review-diff.py` selects the groups below from the paths a
commit records and puts those questions in front of the model before the commit lands; the group
names there and the `**Group**` headings here are one taxonomy authored in two files, and a rename in
either place would silently select nothing. [`tools/ci-guards.sh`](tools/ci-guards.sh) holds
the two sides equal — a name on one side only, or a group carrying no numbered question, fails the
guards.

**Cite a question by number *and* name** — `question 8, *One-way lock*`. A bare number resolves
silently to whatever occupies it after a renumber.

**Layer & recipes**

1. **Documented at the module.** Does the change update the README of each module it touches, and
   the subsystem document where it changes how the modules fit together?
2. **Device-verified.** Has this run on the **bench** board through the bench runner, whose record
   names the board and the commit it ran? A recipe that parses is not a recipe that works.

**Build config & pins**

3. **WebKit cost.** Does this reach WebKit's build, alone or with more
   ([`docs/image.md`](docs/image.md) §"What a rebuild costs")? Then it is a decision taken before
   starting, not one discovered afterwards.
4. **kas block collision.** Is every `local_conf_header` block name unique across the include chain?
   kas merges by block name and the top-level file wins, so a duplicate is discarded with no warning,
   no error, and variables that never reach bitbake.
5. **Pin reachable.** Is every commit a pin names pushed and fetchable by someone who is not you? An
   unpushed pin builds here and nowhere else.

**Upstream patches**

6. **Why not a bbappend.** Does the patch header record what makes this inexpressible from a
   downstream layer, and whether it is suitable to send upstream?
7. **Still applies.** Does the patch still apply to the pinned upstream checkout, against upstream's
   files as upstream writes them?

**RAUC / signing / secrets**

8. **One-way lock.** Is the keyring and `compatible` consequence understood? A deployed board refuses
   a bundle signed by a key it does not trust and refuses a compatible that is not its own — a wrong
   change strands every unit in the field, and there is no remote undo
   ([`docs/updates.md`](docs/updates.md) §"The one-way lock"). The rotation order in
   [`docs/updates.md`](docs/updates.md) §"Rotating the signing key" is not optional.
9. **No secret as a build input.** Does any value `secrets.yaml` holds
   ([`docs/device.md`](docs/device.md) §"Provisioning") become something bitbake reads? That makes one
   image per site, with that site's wireless credentials inside every update bundle.
10. **No identity in the tree.** Does any tracked file gain a value the public-repository rule at the
    top of this file names? Fixtures included: a test that needs an address uses a documentation
    address, not a real one.

**Tooling, guards & CI**

11. **Proved it can fail.** Was the new or edited check watched failing — the defect seeded, the seed
    confirmed to have landed, and the spelled-differently-but-valid variant confirmed to still pass?
    A guard keyed on the same literal as the thing it guards cannot see that thing fail.
12. **The finding's own repro.** Was the reproduction that surfaced the defect re-run against the
    fix, rather than a test written afterwards that resembles it?
13. **Every case, again.** Where a step was added to a sequence, was the whole sequence re-run
    against the cases it already passed — first where those steps share mutable state?
14. **Orphaned names.** Where a recipe, check or workflow step was removed, does any operator-facing
    reference to its name survive that no gate reaches — a justfile `[doc()]`, a workflow step
    `name:`, a `--help` string?

**Docs**

15. **Cross-references resolve.** Does `just links` pass — relative links from the citing file's own
    directory, GFM anchors on real headings, section references by name, no anchored directory link,
    no address?
16. **One home.** Is each fact stated in the document that owns it, and cited rather than restated
    everywhere else? Strip the citation out of the sentence: if what remains still asserts what the
    cited document asserts, it restates rather than cites.
17. **Timeless, and current.** Does the prose describe what the tree does now, with the history it
    replaced left to the issue and pull request rather than kept as a "no longer" clause?
