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
