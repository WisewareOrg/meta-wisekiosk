# Testing

What proves a change is good enough to ship, at each tier, and — just as importantly — what a green
result at that tier does **not** let you conclude.

| Tier | Guarantees | Runs | What green does not say |
|---|---|---|---|
| Static (`just guards`, CI) | Repository invariants hold: no secret or identity reaches a tracked file, shell and YAML parse, every wiring self-test passes. | Every commit (pre-commit hook), every PR and merge-group commit (CI). | Anything about a Yocto build. This tier never invokes bitbake. |
| Host (`just test`) | `meta-wisekiosk/lib/oeqa/runtime/framework/record.py` and every case package's own `verdict.py` under `cases/` behave as their constructed-input tests say, at a 100% line and branch coverage floor. | Every PR and merge-group commit (CI). | That a board actually produces the input these functions expect. That contract is proven separately, by a case's own acceptance runs on bench; `framework/base.py` and each package's `case.py`/`selfcheck.py` are transport only and are outside this tier's coverage population by construction. |
| Build (`just build`) | The kas config resolves and bitbake completes: an image artifact exists. | On demand, locally — never in CI, which does not build. | Whether the image differs from the last one, whether it boots, whether it serves anything. |
| Image content (`just oe-test 127.0.0.1 kiosk_image.case`) | The built rootfs's display-launch unit carries its designed flags (`-s 0 -dpms -nocursor`, drop-ins merged as systemd merges them), the required binaries later checks need are present, and the display's served `index.html` is in the rootfs. Reads the build's own deployed `.ext4` directly — no board, no network, in seconds. | The pipeline, once per queue job, before `send`. | Whether the bundle ties to this image (`reproducibility-gate.sh`'s own job, below), whether the image boots, whether the display actually renders, whether its units are well-formed, or anything the device smoke tier below settles. |
| Device smoke (`testimage` in the pipeline, or `just oe-test <target>` by hand) | The backend unit is active, `/healthz` answers, the page serves, WebKit still composites on the GPU, the page is still painting, the page is applied as the application designs it, the browser comes back on its own when it dies, the display runs at the configured mode, at or above the design floor, and every unit meta-wisekiosk's own recipes ship is loaded with no load error and none failed (`systemctl show`/`systemctl list-units --failed`, against the board's own systemd) — on **one** physical device, one boot. Both run `includes/testimage.yaml`'s own `TEST_SUITES` list of `meta-wisekiosk/lib/oeqa/runtime/cases/kiosk_*.case` modules and write the same run record. | The pipeline, once per queue job, after an OTA install (never a flash). By hand, any time, against any board `local/device-identity.md` names — never prod, which the suite's own hostname check refuses. | The shared boot partition (`config.txt`, `cmdline.txt`, `boot.scr`, and `uboot.env` apart from RAUC's own boot-selection variables) — an OTA writes only the slot rootfs it boots, which does carry the kernel. The RAUC slot layout, which an OTA never touches, or a second boot. |
| OTA/rollback (the queue run) | Install, reboot, and — for a queue run — mark-bad, reboot and land back on the baseline slot all completed, and the device answered again each time. | Every queue job. | Whether the slot rolled back *into* would itself survive a fresh install — it was booted back into, not reinstalled. There are only two slots. |

The Static tier's `docs/requirements/` gate (see [`docs/requirements/README.md`](requirements/README.md))
walks the project root looking for Doorstop documents; `build/` and `sources/` each carry a
`.doorstop.skip-all` marker for exactly this reason, written by guard 23 of `tools/ci-guards.sh` before the gate
runs, once the directory exists and the marker is absent, never committed. A fresh checkout has neither directory, so
nothing is written and nothing is walked. A `build/` or `sources/` already populated from a build that
predates this marker, or large from ordinary use, costs the gate real time regardless of the marker:
Doorstop's own reference search walks every non-ignored file under the project root once per run, and
that walk is slower the larger either directory already is — a known local-dev cost, not a defect.

## Running it

```sh
just pipeline-install                # once per host, idempotent -- reads $DL_DIR, $SSTATE_DIR,
                                      # $PIPELINE_TARGET
just pipeline-on                     # enable the timer
just pipeline-off                    # disable it
just pipeline-status                 # timer state + any DISABLED reason
just pipeline-run                    # one job by hand: the queue head, or a missing baseline
just pipeline-run-ref <ref>          # dev tool: build and run <ref> from this checkout, posting nothing
just pipeline-accept-bench-config    # record bench's current /data as the accepted baseline
just pipeline-watch                  # live view of the merge queue and the current run; q quits
```

`pipeline-run`, `pipeline-run-ref` and `pipeline-accept-bench-config` each call a script that sources
`~/.config/wisekiosk/pipeline.env` itself when `PIPELINE_TARGET` is unset, rather than the recipe
sourcing it first — one place per script, not a line repeated at every call site. `pipeline-run`
calls the driver checkout's own `run.sh`, so that self-sourcing takes effect there once the driver
is running a commit that carries it.

The job is the head of the merge queue — the entry whose own base commit is `origin/main`'s current
tip, since every later entry is built on an earlier one's still-speculative result, not on main — and
a PR enters the queue after its static checks pass and merges only if `bench-pipeline` is green on its
merge-group commit. A lone queue ref whose own base is not that tip is stale — GitHub rebuilds it —
and reads as no job, the same as an empty queue. The host builds and tests whatever a writer enqueues,
including a cross-repository PR: enqueueing is the trust decision, not where the PR came from.

`pipeline-install` is the whole reprovisioning procedure — nothing is done to a host by hand that it
does not also do, except the one-time hash-server setup in [`../README.md`](../README.md) §"Quick start",
which every host needs once regardless of the pipeline. `pipeline-install` creates, all under `$HOME`:

- `wisekiosk-pipeline/driver` — this repository at `origin/main`; runs `run.sh`. Every tick fetches
  it first and, if its HEAD is not `origin/main`, checks that out and restarts itself from the fresh
  copy, so the driver always runs at `origin/main`'s current commit: a change to the driver is
  judged by the driver before it and takes effect once merged. The device checks it runs on the
  board, `tools/kiosk-render-check.sh` and `tools/kiosk-gpu-check.sh`, come from the tree under
  test, so a change to a check is judged by that check. The tick follows that commit; it does not
  reset local edits to the driver checkout. When a driver on `main` cannot judge its own fix, run
  `just pipeline-off`, merge the fix with an admin override of the merge queue, then run `just
  pipeline-on`.
- `wisekiosk-pipeline/tree` — a second, detached checkout of the same repository; the tree under test.
- `wisekiosk-pipeline/driver/local/device-identity.md` — a symlink to the dev tree's own copy;
  `tools/scrub-identity.py --filter` is the only thing that reads it, when a run posts its report.
- `wisekiosk-pipeline/tree/local/keys` — a real, empty directory. The fleet signing key and
  `hmac.key` both live in the dev tree's own `local/keys` (`PIPELINE_KEYS_DIR` below), bind-mounted
  read-only into the build container at `/work/local/keys`; the tree checkout sees them only as
  that mount, and neither file is ever copied into it. The driver checkout, which never runs
  bitbake, reads `hmac.key` straight from `PIPELINE_KEYS_DIR` and has no keys directory of its own.
- `.config/wisekiosk/pipeline.env` — `PIPELINE_DRIVER`, `PIPELINE_TREE`,
  `PIPELINE_SSH_DIR`, `PIPELINE_KEYS_DIR` (the dev tree's own `local/keys`),
  `PIPELINE_TARGET` (the device's address; required, no default), `PIPELINE_TARGET_HOSTNAME` (recorded
  once at install by running `hostname` on the device over the newly-installed pipeline key),
  `PIPELINE_LOCK` (the flock path `pipeline-install` and `run.sh` share), the installing shell's own
  `PATH`, and two caches, overridable at install time: `DL_DIR` and `SSTATE_DIR` (default this
  repository's own `build/downloads` and `build/sstate-cache`, shared read-write with the dev tree's
  ordinary builds to avoid refetching or recompiling what is already there). The build dir itself is
  not recorded here: `run.sh` derives it as `$PIPELINE_TREE/build` — kas's own default for that
  checkout — since it is never independently correct to set it to anything else.
- `.config/wisekiosk/pipeline-ssh/` — a new ed25519 keypair, installed on the device's `authorized_keys`;
  `config`; `known_hosts`. Used only inside the `testimage` stage's container — never `~/.ssh`, which
  also pushes to GitHub. Every other stage that reaches the device — the hostname check, `booted_slot`,
  send/install/reboot/rollback, and the render and GPU checks — uses the host user's own default ssh
  identity as root, which the device must already accept.

The pipeline shares `downloads/`, `sstate-cache/` and the host's one hash-equivalence server with the
dev tree's ordinary builds — see [`../README.md`](../README.md) §"Quick start" for the server's
one-time setup.

Unlike the driver checkout above, `pipeline.env` and the ssh directory are written once by
`pipeline-install` and do not follow `origin/main`. A merged change that needs a new environment
variable needs `just pipeline-install` run again. The units are the driver checkout's own files,
which systemd keeps loaded as they were until `just pipeline-on` re-links them.

It does **not** touch the systemd units — `pipeline-on` enables them by path, the separate,
deliberate step that also links them into the user unit search path.

**The device under test, and the shared `downloads/`/`sstate-cache/`, are reserved while the timer is
on.** A hand `just build` or a manual OTA while `pipeline-on` races the pipeline's own run; `just
pipeline-off` first. The pipeline's own `build/` (TMPDIR) is not shared, so it alone never conflicts
with a hand build.

**Every queue job runs the device tier.** Whatever a PR changes — a recipe, a document, nothing
in the image — its queue job builds, installs on bench, reboots, runs the smoke test and rolls
back.

**The image-content tier runs once per queue job, before `send`, through `just oe-test 127.0.0.1
kiosk_image.case`.** The stage's own log is this tier's record.

**`kiosk-preflight` ties the bundle to the image on every install that runs it** — the pipeline
job, `kiosk-ota`, and both installs of a key rotation (`tools/rauc-rotate.sh`) — by handing both to
`tools/reproducibility-gate.sh --image <ext4> --bundle <raucb>`, which compares the bundle manifest's
own `[image.rootfs]` `sha256=` against a fresh `sha256sum` of the image and refuses on a mismatch.
No bitbake runs in `kiosk-preflight`. Two paths bypass it and ship an untied bundle: `just
rauc-install` (any `.raucb`, checked only `--tree`), and `just kiosk-send-direct` followed by `just
kiosk-install` run by hand.

**The run record.** The suite's own inputs -- `KIOSK_TARGET_ROLE`, `KIOSK_TARGET_HOSTNAME` and
`KIOSK_HMAC_KEY` -- arrive through `testimage`'s `env:` passthrough under the pipeline, or
`tools/oe-test.sh`'s own resolution by hand; the case refuses outright if any is unset.
`KIOSK_HMAC_KEY` names the key's path rather than letting the case derive it from its own
`__file__`, since that resolves to kas-container's `/repo` mount, not `PIPELINE_KEYS_DIR`'s separate
`/work/local/keys` mount (`tools/kas-run.sh`). The suite's base class then writes one record into
`testresults.json`'s
`extraresults` before any case's own assertions run: `tool` (the checkout's own commit and dirty
state, and `argv`, identity-scrubbed), `board` (role, the live-hostname check,
boot id, boot ordinal since the booted slot's install, uptime, start/end), `image` (the booted
slot's `/etc/buildinfo` commit and slot), `app` (the served bundle's asset hashes, a keyed hash of
`config.json`, and its location-free summary), `sut` (the browser process, restart count, its own
cmdline hash, WebKit's env overrides, a keyed `kiosk.conf` hash, mode, kernel, cpufreq cap, timesync
state), and one `page.<case id>` line per DOM-probe case. `boot_ordinal` counts only the booted
slot's own boots since install, from one read across the whole retained history, never one call
per boot: `journalctl -u rauc.service -o json
--output-fields=_BOOT_ID,MESSAGE,__REALTIME_TIMESTAMP`. Each entry's `MESSAGE` names the slot in
that unit's own `Booted into rootfs.<n> (<slot>)` line (the kernel's own `Command line` entry does
not survive this image's early-boot journal rotation, so that line is read instead), and a boot is
counted only when its own `__REALTIME_TIMESTAMP` -- never `--list-boots`' `first_entry`, which the
early-boot clock can floor before NTP syncs -- is at or after the install instant. A boot with no
RAUC line is excluded rather than assumed to match. The two keyed hashes -- `config.json`'s
and `kiosk.conf`'s -- are read as a `hexdump -ve '1/1 "%02x"'` dump, not `cat`: busybox's `od` has
no long options and no `base64` applet exists either, and hex is the one transport a plain text
capture's trailing-newline handling cannot silently lose a byte from, so every reader that computes
one of these hashes -- the record, the `/data` precondition below, and
`pipeline-accept-bench-config` -- decodes the same dump the same way, through `config-mac.py` on
the shell side and `framework.record.decode_hex_dump` directly on the Python side. No address,
hostname, key material, coordinate or park identifier ever reaches it.
It lands wherever the harness writes `testresults.json` — under the driver at
`local/pipeline/runs/<sha>/testresults.json` for a pipeline job, under the path a hand run names
for `just oe-test`. `run.sh` reads it back before posting, through `tools/pipeline/record-check.py`
(which imports the package the way `config-mac.py` does, and prints one line `run.sh` reads with a
single `read`): a missing or malformed record, or an `image=` that is not `$SHA`, is the job's own
failure, never posted as a pass; a dirty tree is an infrastructure failure instead, since it names a
problem with the checkout the job ran from rather than the candidate. Neither check exits non-zero
itself, however malformed the record: the device sits mid-OTA by then, and a script failure under
`set -e` at that point would abort before the unconditional rollback runs.
`report-build.py` renders the record's lines verbatim under their own heading, never as case rows,
so a later change to the record's shape needs no change to this renderer.

**The `/data` precondition.** Before every job, `run.sh` compares bench's `/data/config/kiosk.conf`,
`/data/config/config.json` and `/data/config/replay-ca/ca.crt` keyed hashes against `just
pipeline-accept-bench-config`'s last recorded values, confirms `/data/config/wisekiosk.conf` is
absent, and refuses the job on any difference — a hand edit is an environment problem a person
accepts, not a silent comparison against a stale baseline. `pipeline-accept-bench-config` needs the
timer off; it installs the CA cert from this host's own `local/keys/replay-ca/ca.crt`
([`tools/replay/README.md`](../tools/replay/README.md)) and prints every hash, never a value.

**The buildinfo readback.** After the install reboot, `run.sh` reads the booted slot's
`/etc/buildinfo` back and compares its `meta-wisekiosk` commit to `$SHA`. A mismatch skips
`testimage` and the two device checks — there is no point running the suite against the wrong
image — but still rolls back, like every other outcome, before `finish failure` names the mismatch.

**Replay mode.** `run.sh` can put bench's backend behind the committed replay proxy instead of the
real upstream data sources — [`tools/replay/README.md`](../tools/replay/README.md) owns the proxy,
the CA and the set layout. With `PIPELINE_REPLAY_SET=<name>` set, before `testimage` runs: `run.sh`
starts `tools/replay/replay.py` on loopback, holds a reverse `ssh -R` tunnel to bench for the job's
own duration (never `tools/kiosk-ssh.sh`'s persistent shared master, which would outlive the job),
seeds bench's `/data/config/wisekiosk.conf` (`HTTPS_PROXY` at the tunnel, `SSL_CERT_FILE`/
`SSL_CERT_DIR` at the installed CA) and the set's own `config.json`, restarts `wisekiosk.service`
and reads its mode from `/proc/<MainPID>/environ`, then restarts `kiosk.service` so the page loads
afresh against replay before `testimage` runs. `PIPELINE_REPLAY_SET` unset is a live run: no proxy,
no tunnel, no seed, and the mode is still read the same way (absent `HTTPS_PROXY` confirms "live"),
voiding the job if it reads anything else.

After `testimage` — which is where the applied case's own `cards=<present>/<live>` lands in the
record, as a recorded field only, never a comparison (the sample is taken at `state=applied`,
before the park modules' own fetch fills the cards, so comparing it against a set's expectation
would void good jobs) — `run.sh` re-reads the mode on every job, live or replay, and voids if it no
longer matches the start; a replay job also checks the proxy and tunnel are still alive and the
access log carries zero `MISS` lines and at least one `HIT` line (the request reaching the proxy
over the tunnel). It then restores bench's own `config.json`, confirming no `HTTPS_PROXY` remains,
before stopping the proxy and tunnel. A mismatched mode, a `MISS`, or a dead proxy or tunnel each
sets a flag; `run.sh` reads every such flag only once execution reaches the point below that
already reads `DIRTY_RC`/`TRANSPORT_RC` — the same reason a dirty tree never calls `abort` before
the unconditional rollback runs. The mode run.sh measured — `live` or `<set>@<manifest-hash>`, the
hash read from the proxy's own startup log line, never recomputed — is written into the record
itself as a new `replay` key, through `record-check.py --replay`, before `report-build.py`'s own
unchanged passthrough renders it.

**`pipeline-run-ref <ref>` is a development tool, not a path to `main`.** Run from a branch
checkout with the timer off, it builds and runs that ref's own head through the same stages as a
queue job — using that checkout's own `run.sh`, never the driver's — and posts no status, writes no
PR comment and tags no baseline, because no merge-queue entry is under test. The merge gate still
reads only `main`'s queue, judged by `main`'s driver.

**The baseline tag advances on every successful queue job.** A queue job that posts `success` —
on a device run whose smoke test passes — tags its own buildhistory commit `baseline/<sha>`; an
existing tag is left as is. A baseline build
runs only when the job's base commit has no such tag: it resets `build/buildhistory` to
`refs/tags/baseline/<sha^1>` (main's previous tip) when that tag exists, left alone otherwise —
an ejected candidate's own job tag is never picked up this way — builds the missing commit, tags its
own buildhistory, and stops — no status is posted and no PR comment is written, because no job's own
commit is under test. The next tick picks up the queue job against the tagged baseline.
`pipeline-run-ref` never builds or tags a baseline, and never posts, for any ref including `main`
itself: a missing tag there is a refusal naming it and the fix, not a silent build. The fix is a
queue job on `main`, which tags as it merges — that is the only path that names the tag a dev-tool
run can rely on finding.

**Each queue job's buildhistory starts from the baseline tag.** Immediately before the job's own
build, `build/buildhistory` is reset to the job's base commit's tag, so the build's own
version-going-backwards check never compares against another candidate's leftover packages.

**Records** live at `local/pipeline/runs/<sha>/` under the driver: the build log, each OTA stage's
log, `testresults.json`, and the assembled report body.

**An infrastructure failure** — the device unreachable, the device's live hostname not matching the
recorded `PIPELINE_TARGET_HOSTNAME` (§"The hand-run path" names the
same refusal for the hand-run suite), the shared
bitbake-hashserv not answering before a build, the job's base commit not resolving, a baseline build
failing, the rollback reboot never coming back, the rollback not landing back on the pre-install slot,
a report or status failing to post, or the process exiting for any other reason while the device sits
mid-OTA — writes `local/pipeline/DISABLED` under
the driver with the reason and disables the timer. Nothing loops silently. Fix the cause, then `just
pipeline-on` -- it prints the DISABLED reason and clears the file itself, as an explicit
acknowledgement, before re-enabling.

A job's own build, bundle, image-content, preflight, send or install failing, or the device not
booting the new slot,
are not infrastructure failures: each posts its own status (`failure`) on the job's commit with a PR
comment carrying the failing logs, and the timer stays on for the next job. An install failure
additionally waits for the installer to go idle, then marks the other slot bad, over ssh before
posting, best effort: polled every 10 s for up to 10 min, and if it never goes idle or the device is
unreachable, the attempt is logged and the run still finishes. A missing buildhistory tag for the
baseline commit is not a failure either: it selects a baseline build for that commit instead of a job
run.

`PIPELINE_TARGET`, `PIPELINE_TARGET_HOSTNAME` or `PIPELINE_TARGET_ROLE` unset refuses the run outright
(rc 2) without touching the timer — a `pipeline.env` configuration problem, like any other required
variable missing, not an infrastructure failure. More than one merge-queue ref based on
`origin/main`'s tip refuses the same way (rc 2, timer untouched): the ambiguity is visible only in
the timer's own log, with no DISABLED file and no PR comment.

A new host needs a clone, the dev tree's `local/device-identity.md`, `gh auth login`, the host user's
own ssh identity already accepted as root on the device, and `just pipeline-install`.

## The hand-run path

Each device test lives in its own package under `cases/` (a directory carrying its own
`__init__.py`); the pinned poky oeqa loader discovers one the same way it discovers any other
layer's oeqa extension, and `TEST_SUITES` / `--run-tests` select a package by its own top-level
name. The mechanism is precise, and every case's own imports depend on it: for each layer that
carries one, the loader hands Python's own `unittest.TestLoader.discover()` that layer's
`lib/oeqa/runtime/cases` directory itself as both `start_dir` and `top_level_dir` — so `kiosk_render`
and so on resolve as bare top-level packages rooted at that directory. The shared base and record
parsing every case needs is not itself a case, so it is not under `cases/` at all: it lives in
`meta-wisekiosk/lib/oeqa/runtime/framework/` (`base.py`'s `WiseKioskCase`, `record.py`), made
importable as bare `framework` by `layer.conf`'s `addpylib ${LAYERDIR}/lib/oeqa/runtime framework` —
the same `addpylib` mechanism other layers use to make their own oeqa extensions importable (poky's
own `meta/conf/layer.conf` declares `addpylib ${LAYERDIR}/lib oe`, and other layers in the pinned
tree, such as meta-arm and meta-selftest, declare their own `addpylib ... oeqa`), here with
`lib/oeqa/runtime` as the libdir and `framework` as the namespace rather than `oe` or `oeqa`.
`cases/` itself is a separate, poky-managed path and needs no `addpylib` of its own:
`testimage.bbclass`'s own `get_runtime_paths()` builds it directly from `BBLAYERS`, hardcoded,
independent of this mechanism. A `case.py` therefore imports a sibling module in its own package
with a
relative import (`from . import verdict`) and the shared base or record parser by its bare top-level
`framework` name (`from framework.base import WiseKioskCase`, `from framework import record`) —
never `oeqa.runtime.cases.*` or `oeqa.runtime.framework.*`, neither of which resolves here, and will
not be caught by a hand run whose `PYTHONPATH` also carries the broader `meta-wisekiosk/lib` (below):
that extra entry would let a nested form resolve too, through ordinary namespace-package merging,
passing what testimage itself refuses. Every reader outside this tree runs on the host instead: the
pytest fixtures under each per-test package's own `tests/` (testing that package's `verdict.py`) keep
`oeqa.runtime.cases.<package>.verdict`, since that module never moved; `framework/tests/` (testing
`record.py`) and the pipeline driver scripts under `tools/pipeline/` import bare `framework.record`,
with `meta-wisekiosk/lib/oeqa/runtime` on `sys.path` directly rather than through `addpylib`, which
only bitbake itself evaluates.

`tools/oe-test.sh <target-ip>` runs the identical suite — `includes/testimage.yaml`'s own `TEST_SUITES`
list of `meta-wisekiosk/lib/oeqa/runtime/cases/kiosk_*.case` modules, each with the pure
`verdict.py`/`record.py` beside the `case.py` it serves — with `oe-test runtime`, no bitbake, no OTA,
against any board already built and booted. It resolves `KIOSK_TARGET_ROLE` and
`KIOSK_TARGET_HOSTNAME` from `local/device-identity.md` (the role whose recorded address is
`<target-ip>`, and bench's own recorded hostname — the suite refuses any board that is not bench
regardless), refuses with a message if the HMAC key, the identity file, `sources/poky`, or the
last build's deploy artifacts are missing, and writes its own run record under gitignored
`local/oe-test/<timestamp>/`. It never touches RAUC, never installs, never reboots: of the suite's
own cases, only two change anything on the board — `test_page_applied` arms the DOM probe
(`copyTo` the script, restart `kiosk.service`), which its own teardown removes before the case
ends, and `test_browser_restart` arms the same probe, restarts `kiosk.service` to take its
baseline, then kills the browser and waits for it to come back.

To run one checker's self-test instead of the suite, see the `selfcheck.py` bullet in
[`cases/README.md`](../meta-wisekiosk/lib/oeqa/runtime/cases/README.md).

Its `PYTHONPATH` is exactly testimage's own, nothing broader: `sources/poky/meta/lib` and
`sources/poky/bitbake/lib`, plus `meta-wisekiosk/lib/oeqa/runtime` — the hand-path twin of
`layer.conf`'s `addpylib`, making `framework.base`/`framework.record` resolve the same way
`addpylib` does under testimage. The broader `meta-wisekiosk/lib` is never on it: carrying it would
let a nested `oeqa.runtime.cases.*`/`oeqa.runtime.framework.*` form resolve too, through ordinary
namespace-package merging, masking a case whose cross-package import testimage itself would refuse.
`bitbake/lib` is needed beside `meta/lib` because `oe-test`'s own component loader imports every
subcommand's context module up front, including one that imports `bb.utils` at module scope,
regardless of which subcommand is actually requested; `meta/lib` for `oeqa.runtime.case` and
everything else poky's own oeqa package provides. The directory passed on `oe-test`'s own command
line (`meta-wisekiosk/lib/oeqa/runtime/cases`) becomes its `top_level_dir` the same way testimage's
own run does: the two sys.paths match exactly, so a case whose cross-package import testimage
refuses fails the identical way here. It also runs from inside its
own `local/oe-test/<timestamp>/` directory, so poky's own ssh target class — which writes
`remoteTarget.log` into whatever directory the process started in, with no flag to redirect it —
leaves that file beside the run's own record instead of in the repository root.

## The render and applied cases

Each lives in its own package: `kiosk_render/` holds `test_render_advancing` beside the verdict it
calls, `kiosk_applied/` holds `test_page_applied` beside `probe.js` and the title parser/verdict it
calls — `meta-wisekiosk/lib/oeqa/runtime/cases/README.md` states the layout every case package
follows.

`test_render_advancing` captures a small region (`560x300+220+20`, aimed at the clock's own
seconds field) rather than the whole screen: a full-screen capture costs about 8 s per frame on
this board against roughly 1.4-2.4 s for the crop, and two full frames plus the interval would be
load on the thing being measured, not a measurement of it. The crop assumes the kiosk page always
has a moving element inside the captured region; today that element is the clock's seconds field.
`import`'s own stderr is kept, not discarded, and folded into the error reason when `import` itself
fails, rather than left to read "exited non-zero" with no further detail. The two captures are
judged by `kiosk_render.verdict.verdict`, a port of the same probe's own guards.

`test_page_applied` reads the page's state back through `document.title`, because surf's console
does not reach the journal on this image: the DOM probe writes its state there on every finished
load and every 5 s after, and the case reads it back over ssh with `xwininfo -tree` (surf sets
override-redirect, so its window carries no `_NET_*` properties and is absent from the client list)
and `xprop`'s `WM_NAME`, the same channel `kiosk-bootprof`'s `measure-surf.sh` already reads. Its
own teardown removes the probe script it deployed, without restarting `kiosk.service` — the file is
gone before any later boot or restart would load it again, though the already-running process it
armed keeps running until then.

A deploy, probe or transport error is retried once; a second one declares the page line's state
`error:transport` before raising. `run.sh` reads that declared kind, after rollback (bench is never
left on the installed slot with the timer disabled), and treats it as an infrastructure failure —
`abort`, never posted on the candidate — where any other error or failure is the job's own.
