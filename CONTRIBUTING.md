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
is gitignored and written at build entry instead of checked in; which files those are is
[`docs/image.md`](docs/image.md) §"Building". A pin is never autogenerable, so a pin — a layer
commit, `pyproject.toml` and `uv.lock` — is committed.

## Running the checks

```sh
just                # the recipe roster, each beside what it does
just check          # every check CI runs, stopping at the first failure
just verify         # `just check`, then the docs against what the built image ships
just install-hooks  # once per clone: point core.hooksPath at .githooks
```

`just check` runs five checks: `pytest tests/prechecks` (the self-tests of the device guard, the CVE and
host-side tools and the screenshot decoder, plus the one-install-path test),
[`tools/doc-links.py`](tools/doc-links.py), [`tools/scrub-identity.py`](tools/scrub-identity.py)
`--check`, wise-ci's `check-reqs` over the requirements tree
([`docs/requirements/README.md`](docs/requirements/README.md)) and `check-adrs` over
[`docs/decisions/`](docs/decisions/README.md) and every ADR citation. The pre-commit hook and CI's
`guards` workflow both run it, so a commit cannot pass locally and fail there on them. CI adds a
gitleaks scan of the history. The `lint` workflow runs shellcheck over every tracked shell script
and actionlint over the workflows, and `codeql` analyses the tooling. `just verify`'s second half
needs a populated `build/` and is local-only: CI never builds.

`tools/scrub-identity.py --check` has two halves and says which ran. The pattern half needs no
configuration and runs everywhere. The known-value half reads `local/device-identity.md`, which is
gitignored and therefore absent in CI — so a run there reports PARTIAL, never "clean". A hostname or
an SSID has no recognisable shape; only the map can catch one, and only where the map exists.

**A PARTIAL scan exits 1.** A run that could not perform half its search must not return the code
for "nothing found", so the absence of the map is a finding wherever the map could exist. The one
caller that structurally cannot hold it — CI, which clones without `local/` — passes
`just check --allow-partial` and carries the reason in its own step. On a checkout with no map the pre-commit
hook and `just check` therefore fail where CI passes: create `local/device-identity.md`, or pass
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
holds a choice that took a trade study, with the alternatives it rejected. No tracked document
describes a particular board: what it runs, which slot it is on, its role, or what may be done to it.
That setup lives only in the gitignored `local/`. A rule that holds for every board, such as how a
test reaches one, is not such a description.

**The tree describes the system; issues and pull requests are the record of the work.** A recipe, a
class or a justfile says what the tree does, and a document says how the system is built and
why. How a problem was traced to its cause and fixed stays on its issue and pull request; a design
choice, with the alternatives it rejected and why, goes in its ADR
([`docs/decisions/`](docs/decisions/README.md)). Neither goes in a comment or a "no longer" clause.
State the timeless fact — no *now*, *no longer*, *as of*.

**A comment states what or how, in one or two present-tense lines, only where the code does not show
it.** No why, no history, no issue numbers, no attributions. The deletion test decides: delete the
comment, and if the reader loses no mechanism fact the code does not show, it stays deleted. A
current fact that explains a module belongs in that module's README. A tool's usage or `--help` text
and a docstring that gives usage, knobs and the exit contract are documentation, not comments.

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

## Justfile conventions

- **A recipe is its attributes and a few plain lines.** Every listed recipe carries `[group()]`, then
  `[doc()]`, and a body that is a call to one tool or a short sequence of `just` and tool calls. No
  `if`, `case`, loop, `trap`, heredoc or `ssh` goes in a justfile: anything of that kind is a
  `tools/<recipe>.sh` that the recipe calls in one line.
- **A justfile carries no comments.** `[doc()]` is the documentation, and a fact a reader needs goes
  in the doc text or in the document that owns it. A sub-justfile has one header line listing the
  variables it reads. `help` stays ungrouped at the top of the list and `default` is `[private]`.
- **Groups** are build, clean, check, audit, deploy, provision, ota, device and rotate. `device` holds
  the looks at a board and the boot-profile launcher; `ota` holds whatever changes a board's slots.
- **A recipe that reaches a board takes `host=kiosk-host`**, in the `root@<addr>` ssh-target form
  that [`docs/device.md`](docs/device.md) §"Reaching a board" owns. `rotate-run` and `rotate-verify`
  keep `host` required: a default would let `KIOSK_HOST` pick the board for a keyring change.
  `tcp-state`'s `kiosk-addr` is exempt, because it reads this host's sockets.
- **Nothing in a recipe or a tool opens a connection to a board except
  [`tools/kiosk-ssh.sh`](tools/kiosk-ssh.sh)**, which holds the one host-key policy and keepalive. A
  recipe reaches a board through that helper or through a `tools/` script that uses it. The one
  exception is the interactive first contact in `tools/rauc-provision-ssh.sh`, which may ask for a
  password.
- **Python tools run through `{{py}}`.**
- **Names are kebab-case and say what the operator gets.** Families share a prefix: `kiosk-` for one
  board's state, plus `rotate-` and `cve-`. A new wrapped tool takes the recipe's name. Existing names
  stand, because tests and docs call them.

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
which is why `.claude/hooks/guard.sh` and the CVE and currency tools ship with self-tests in
[`tests/prechecks/`](tests/prechecks/), which `just check` runs.

## Review checklist

Each question is an obligation on the author that leaves no artifact, so no check decides it — the
reviewer is the mechanism. `.claude/hooks/review-diff.py` selects the groups below from the paths a
commit records and puts those questions in front of the model before the commit lands; the group
names there and the `**Group**` headings here are one taxonomy authored in two files, and a rename in
either place would silently select nothing.

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
4. **kas block collision.** Is every `local_conf_header` block name unique across the include chain
   ([`docs/image.md`](docs/image.md) §"What kas does")?
5. **Pin reachable.** Is every commit a pin names pushed and fetchable by someone who is not you? An
   unpushed pin builds here and nowhere else.

**Upstream patches**

6. **Why not a bbappend.** Does the patch header record what makes this inexpressible from a
   downstream layer, and whether it is suitable to send upstream?
7. **Still applies.** Does the patch still apply to the pinned upstream checkout, against upstream's
   files as upstream writes them?

**RAUC / signing / secrets**

8. **One-way lock.** Is the keyring and `compatible` consequence understood
   ([`docs/updates.md`](docs/updates.md) §"The one-way lock"), and does a key change follow the
   order in [`docs/updates.md`](docs/updates.md) §"Rotating the signing key"?
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

15. **Cross-references resolve.** Does `just check` pass — relative links from the citing file's own
    directory, GFM anchors on real headings, section references by name, no anchored directory link,
    no address?
16. **One home.** Is each fact stated in the document that owns it, and cited rather than restated
    everywhere else? Strip the citation out of the sentence: if what remains still asserts what the
    cited document asserts, it restates rather than cites.
17. **Timeless, and current.** Does the prose describe what the tree does, with the history it
    replaced left to the issue and pull request rather than kept as a "no longer" clause?
