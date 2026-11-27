# Contributing to meta-wisekiosk

The human contributor entry point: how to run the checks, what the conventions are, and how a change
gets merged. **What this repository is** and how to build, flash and update is the
[README](README.md), which also holds the only index of the repository's documents. Working rules for an AI agent are in [`CLAUDE.md`](CLAUDE.md).

**This repository is public.** No device address, hostname, SSID, PSK hash, MAC, serial or machine-id
belongs in a tracked file — not in a doc, not in a test fixture, not in a comment. None of it is
credential-shaped, so no secret scanner stops it, and together it fingerprints one network. The real
values live in gitignored `local/device-identity.md` and in `~/.config/wisekiosk/secrets.yaml`; the
tree refers to them by role (`prod`, `bench`) and discovers an address at use time with
`just find <cidr>`.

## Before you change anything

**Build with `just build`, never `kas-container` directly.** `just build` writes
`meta-wisekiosk/conf/build-rev.inc` first; calling kas straight skips that, and on a tree that has
built before you build against the *previous* run's commit — an image the reproducibility gate then
refuses at flash. See [`README.md`](README.md) §"Quick start".

**Touching webkit's `PACKAGECONFIG` invalidates WebKit alone; touching `DISTRO_FEATURES`,
`MACHINE_FEATURES`, or bumping the poky or meta-openembedded pin, invalidates more than WebKit.**
Either is a multi-hour rebuild — see [`README.md`](README.md) §"Quick start" for the measured
costs — so it is a decision made before starting, not a tweak. `config.txt`-only knobs are free.

**Two boards, two roles.** `prod` is wall-mounted and carries the live soak run; `bench` is the
board to OTA, reboot and abuse. Nothing destructive goes near prod, except under a time-boxed
`tools/prod-authorize.sh` grant, which widens only OTA, install, reboot, rollback and reprovision —
flash, `tools/rauc-rotate` and any power-off verb stay blocked regardless.
`.claude/hooks/guard.sh` enforces both halves, but only as a backstop — and only as far as
`local/device-identity.md` is current, so update that file when a board is swapped.

**Nothing autogenerable is committed (owner, 2026-09-27).** A file this tree can regenerate from what
is already pinned is gitignored and written at build entry instead of checked in —
`meta-wisekiosk/conf/build-rev.inc` was the first of these; `wisekiosk-backend-go-mods.inc` and
`wisekiosk-frontend/npm-shrinkwrap.json` are written the same way, by `tools/go-mods.py` and
`tools/app-lockfile.py`. Bumping the WiseKiosk app pin is therefore a one-line `SRCREV` edit — see
[`meta-wisekiosk/recipes-wisekiosk/wisekiosk/README.md`](meta-wisekiosk/recipes-wisekiosk/wisekiosk/README.md).
A pin on the repository's *own* tooling is the opposite case: `pyproject.toml`/`uv.lock` fix the
versions of PyYAML and anything else `tools/*.py` imports, the same way `includes/base.yaml`
fixes a layer commit, and a pin — unlike a build-derived file — is never autogenerable, so it belongs
in the tree (#167 restore pinned Python tooling).

## Running the checks

```sh
just                # the recipe roster, each beside what it does
just verify         # every documentation check: cross-references + docs-vs-image
just links          # cross-references only (this is the one CI requires)
just guards         # repository invariants: secrets, identity, syntax, wiring;
                    # runs the self-tests of the device guard, the CVE tools and the host-side tools too
just reqs           # the requirements tree, through wise-ci's check-reqs
just adrs           # docs/decisions/ and every ADR citation, through wise-ci's check-adrs
just install-hooks  # once per clone: point core.hooksPath at .githooks
bash .claude/hooks/guard-test.sh   # the device guard's self-test on its own
```

CI runs [`tools/ci-guards.sh`](tools/ci-guards.sh),
[`tools/scrub-identity.py`](tools/scrub-identity.py) `--check` and
[`tools/doc-links.py`](tools/doc-links.py). The pre-commit hook runs the same three, so a commit
cannot pass locally and fail there on them. CI also runs two wise-ci checks the hook does not:
`check-reqs` over the requirements tree, which
[`docs/requirements/README.md`](docs/requirements/README.md) covers with its gate, and `check-adrs`
over [`docs/decisions/`](docs/decisions/README.md) and every ADR citation. `just image` and
`just verify`'s second half need a populated `build/` and are local-only: CI never builds, and a
required check that skips on every run is noise rather than a gate.

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
that do, what each one actually proves, and how to run `bench` behind the device tier.

## Documentation conventions

**Colocation, and one owner per fact.** Documentation lives beside the code it explains — a recipe's
README is as much documentation as anything under `docs/`. State a fact in the document that owns it
and cite it from everywhere else; the index in [`README.md`](README.md) §"Documentation" says which
document answers which question. A second independent statement goes stale in
one copy while the other stays right, with nothing comparing them.

**The tree describes the system; issues and pull requests are the record of the work.** A recipe, a
class or a justfile says what the tree does today, and a document says how the system is built and
why. How a problem was traced to its cause and fixed stays on its issue and pull request; a design
choice, with the alternatives it rejected and why, goes in its ADR
([`docs/decisions/`](docs/decisions/README.md)). Neither goes in a comment or a "no longer" clause.
State the timeless fact — no *now*, *no longer*, *as of*.

**Cite a section by name, never by line number.** A section reference is a Markdown link to the
file, then `§`, then the heading in double quotes — as [`README.md`](README.md) §"Quick start" is
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
either place would silently select nothing. [`tools/ci-guards.sh`](tools/ci-guards.sh) guard 13 holds
the two sides equal — a name on one side only, or a group carrying no numbered question, fails the
guards.

**Cite a question by number *and* name** — `question 8, *One-way lock*`. A bare number resolves
silently to whatever occupies it after a renumber.

**Layer & recipes**

1. **Documented at the recipe.** Does the change that was acted on carry its explanation at the
   recipe, class or bbappend holding it, rather than in a document that has to be found?
2. **Device-verified.** Has this run on real hardware, on the **bench** board, and does the report
   name the board role and the image commit it ran? A recipe that parses is not a recipe that works.

**Build config & pins**

3. **WebKit cost.** Does this touch webkit's `PACKAGECONFIG` or a WebKit recipe (invalidates
   WebKit alone)? Or `DISTRO_FEATURES`, `MACHINE_FEATURES`, or a poky/meta-openembedded pin bump
   (invalidates more than WebKit)? Either is a multi-hour rebuild — see [`README.md`](README.md)
   §"Quick start" — so it is a decision to take before starting, not one to discover afterwards.
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
   change strands every unit in the field, and there is no remote undo. The rotation order is in
   [`docs/rauc-key-rotation.md`](docs/rauc-key-rotation.md) and it is not optional.
9. **No secret as a build input.** Does any site value — SSID, PSK hash, URL, hostname, machine-id,
    nameserver — become something bitbake reads? One image per site, and that site's wireless
    credentials inside every update bundle.
10. **No identity in the tree.** Does any tracked file gain an address, hostname, SSID, MAC, serial
    or machine-id? This repository is public and none of it is credential-shaped. Fixtures included:
    a test that needs an address uses a documentation address, not a real one.

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
