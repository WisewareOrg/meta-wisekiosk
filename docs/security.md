# Vulnerabilities and pin currency

The exposure of this appliance is in the thousands of packages BitBake assembles into the rootfs — a
browser engine, a TLS library, an init system, a kernel — each pinned by an upstream recipe and each
ageing at its own pace. Static analysis of this repository's own scripts sees none of that. This
document is how the image's contents are listed, how their published vulnerabilities are found, and
how far behind upstream the pins have fallen.

Every report here is read by a person and decides nothing on its own: each exits 0 whatever it finds,
and exits 2 when it cannot complete, so a report that measured nothing never reads as a clean one.

| Question | Command | Needs |
|---|---|---|
| What is in the image? | `just sbom` | a build |
| Which packages carry published CVEs? | `just cve-build`, then `just cve` | an audit build |
| What did a second scanner find that the first had no record of? | `just cve-scan` | an audit build, Docker |
| Which kernel CVEs touch code this kernel compiles? | `just kernel-cve` | an audit build |
| What changed since the last audit build? | `just cve-delta` | two audit builds |
| Has upstream moved past the pins? | `just currency` | network |
| Is a newer recipe already in a pinned layer? | `just preferred-version` | `sources/` |
| What would bumping one pin close? | `just gap <repo>` | `sources/`, an audit build |

## The two artifacts

The **SBOM** is a set of SPDX documents, one per built package, written by `create-spdx` on every
build at no extra cost. `kiosk-zero-w.yaml` names the class itself, so a bump of the distro or poky
that stopped inheriting it would not silently drop the SBOM.

The **CVE manifest** lists every CVE that NVD associates with a package version in the image.
`cve-check` writes it, and it is not part of an ordinary build: it needs a local copy of the NVD
database, a network dependency the reproducible build should not carry. It lives in the overlay
[`includes/cve-audit.yaml`](../includes/cve-audit.yaml), and `just cve-build` runs the ordinary
build with that overlay joined on. The audit build changes no recipe's output, so it is incremental
over an ordinary build; its slow part is the first NVD download, which an `NVDCVE_API_KEY` in the
build host's environment speeds up, and which no tracked file or CI holds. The image it produces is
for scanning, not flashing.

Both artifacts land in the gitignored `build/tmp-<machine>/deploy/`. `tools/cve-report.py` and
`tools/sbom-report.py` read the newest build whichever of its names is reached, and print the
artifact's build time beside their counts.

## Reading the CVE report

`just cve` opens with roll-ups — unpatched findings by layer, by package and by severity, the mix of
reasons behind every *Patched* and *Ignored* judgement, and **coverage** — then lists each unpatched
finding. The roll-ups answer which pin bump would help, which a flat list cannot. Filters narrow the
listing only; the roll-ups always count the whole manifest.

**Coverage bounds the blind spot.** `cve-check` writes no record for a recipe it found no CVEs for,
so a recipe with no NVD mapping looks exactly like a clean one. Coverage reads the manifest's JSON
twin and the build's package-to-recipe map to count recipes checked with records, recipes checked
with none, and installed packages whose recipe was never checked. Two known members of that last
class:

- The engine. The pinned `wpewebkit` recipe sets no `CVE_PRODUCT`, while NVD files WPE's CVEs under
  `wpe_webkit`, so no CVEs for the engine is not a finding of none
  ([ADR 0001 rev 2](decisions/0001-wpe-webkit-on-drm-with-our-own-launcher.md)).
- The application's own dependencies. Neither the backend's Go module graph nor the frontend's npm
  closure reaches `cve-check` in a form a CPE lookup matches, tracked as #93 App dependency CVE blind
  spot. The Go modules that build the code generator do appear in the SBOM, as download packages of
  `wisekiosk-backend`, but they build a tool that never ships, so a finding against one is not a
  finding against the board.

**`CVE_STATUS` is the human judgement.** `cve-check` decides *Patched* and *Unpatched* itself, from
versions and patch file names. *Ignored*, and any correction of its verdict, is a `CVE_STATUS` set in
the recipe or bbappend that owns the package, never in a config fragment: a reason keyword
(`cpe-stable-backport`, `not-applicable-config`, `vulnerable-investigating`, …), which poky's
`cve-check-map.conf` maps to a status, and a sentence saying why. The sentence is what lets the next
reader tell a considered judgement from a wave-through.

Nothing here ranks risk. A count of unpatched CVEs is not a risk assessment for a board that shows
one page on a LAN; triage is a person reading the list.

## The second scanner

`cve-check` is the authority, and the only scanner that can read `CVE_STATUS`. A second one is useful
for what the first had no entry for at all. `just cve-scan` scans the SBOM with Grype, whose database
draws on GHSA and other non-NVD sources, and prints only the package-and-CVE pairs the manifest does
not already hold. Both artifacts must come from one build, and the scan refuses a pair whose build
stamps differ.

Grype does not follow SPDX's references between documents, so the script merges the image's closure
of packages into one document; and `create-spdx` writes CPE references in a long form Grype's reader
silently ignores, so the merge rewrites them. Either step skipped gives a scan that runs clean and
finds nothing, so the scan refuses when no package carries a CPE Grype will read, and when a scan
comes back with no matches at all. The scanner and the kas image that unpacks the roll-up are pinned
in [`tools/cve-scan.py`](../tools/cve-scan.py); Grype's database is cached under `~/.cache/grype`
and refuses to run once it is five days old.

## The kernel's compiled sources

The kernel dominates the findings because `cve-check` scores it against the whole Linux tree, and
this board compiles a small part of it. `just kernel-cve` crosses the kernel CNA's list of the files
each CVE touches with the files the audit build compiled (`SPDX_INCLUDE_COMPILED_SOURCES`, set in the
audit overlay), through poky's own `improve_kernel_cve_report.py`, and writes a new report under
`~/.cache/wisekiosk` without touching the manifest. It separates what the file list removed from the
CNA's own re-judgement of each CVE. It needs the CNA's database cloned to
`~/.cache/wisekiosk/linux-vulns` and Python's `packaging`. It counts the compiled files itself and
refuses when there are none or when its count disagrees with the filter's, and it exits 2 with the
helper's own error when the upstream script fails, rather than printing a partial count.

## The delta between audit builds

What is actionable is what changed since the last audit build. `just cve-build` snapshots each
manifest, keyed by the commit, machine and build stamp of the build that wrote it, under
`~/.cache/wisekiosk/cve-history/`; `just cve-delta` reports findings added, removed and changed
between the two newest, each labelled by why it moved:

| Label | What moved |
|---|---|
| `software` | the package's version changed between the two builds |
| `annotation` | the version held; a `CVE_STATUS` judgement shipped in a layer changed it |
| `feed` | package and judgements unchanged; NVD's knowledge changed |

The three look identical in a plain diff and call for different responses: a software move is this
repository's own doing, an annotation move is someone's shipped judgement — the usual effect of a
poky bump on a stable branch — and a feed move is the outside world learning something about an
image that did not change. Because the CVE manifest truncates versions, a version is read from the
image's package manifest through the build's package-to-recipe map where it can be, and every case
the artifacts cannot compare fails towards `feed`.

## Pin currency

A kas `commit:` is not a package manifest, so no generic tool reads it.
[`../renovate.json`](../renovate.json) reads the pins with a regex for the self-hosted Renovate in
`WisewareOrg/wise-renovate`, which keeps one pull request per pin that is behind and rolls it forward
while it stays unmerged; poky and meta-webkit share one ([`image.md`](image.md) §"What a rebuild
costs"). Those pull requests merge through the merge queue, gated by the bench's build of the queued
commit ([`testing.md`](testing.md)). Renovate says *that* a pin is behind; three reports say what it
is worth.

- **`just currency`** asks each remote for the head of the branch its pin tracks, and prints one line
  per pin, `behind` or `current`, ranked by how many CVE-bearing recipes the pin's layers contribute
  to the newest manifest. A pin whose layers contribute none — one enabled only to satisfy a layer
  dependency — reads `dependency only`, so bumping it is visibly worth nothing. It finds the pins by
  scanning `includes/` for `repos:` blocks, so a new pin is covered without a change here, and it
  refuses a repository pinned two different ways across files. Where `sources/` holds a clone, it
  adds how far behind the pin is, or that the pin is not an ancestor of the head. It compares pins,
  not recipe versions: a pin on its head still carries whatever versions that branch froze.
- **`just preferred-version`** reports where a `PREFERRED_VERSION` selects an older recipe than one
  already checked out beside it in a pinned layer, naming the file that sets it. It compares the
  version in recipe file names and does not read BitBake's override chain, so a finding from another
  machine's configuration is about that machine; settings it cannot resolve are listed as unread,
  never dropped. Whether to take a newer recipe is a person's call — for the kernel a large one.
- **`just gap <repo>`** walks the commits between a pin and its branch head in `sources/`, collects
  the CVE ids they name, and intersects them with the unpatched findings: what a bump would plausibly
  close. "Plausibly", because a commit naming a CVE is intent, not proof; the authoritative answer is
  bumping the pin and re-running `just cve-build`. It never fetches unless given `--fetch`, so an
  empty range offline says that upstream has nothing new or that the clone was never fetched, and the
  report names both.

None of the three edits a file. The procedure for moving a pin is [`image.md`](image.md) §"Bumping a
pin".

## What is not covered

The scans run on a build host when somebody runs them, and nothing gates on them: CI never builds the
image, and a required check that can never run would read green while measuring nothing. Nothing
detects that the last audit build was months ago, and a stale manifest reads like a fresh one, which
is why the reports print their artifact's build time. A scheduled scan and a freshness bound are the
rest of #61 Epic: image CVE scanning & SBOM. Checking recipe versions against upstream release feeds
is #81 Investigate a scoped devtool check-upgrade-status recipe-currency target.
