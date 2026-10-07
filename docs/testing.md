# Testing

What proves a change is good enough to ship, at each tier, and — just as importantly — what a green
result at that tier does **not** let you conclude.

| Tier | Guarantees | Runs | What green does not say |
|---|---|---|---|
| Static (`just guards`, CI) | Repository invariants hold: no secret or identity reaches a tracked file, shell and YAML parse, every wiring self-test passes. | Every commit (pre-commit hook), every PR and merge-group commit (CI). | Anything about a Yocto build. This tier never invokes bitbake. |
| Host (`just test`) | `meta-wisekiosk/lib/wisekiosk`'s evaluator functions — the run record's builders and parsers, the render verdict, the applied-page title parser and verdict — behave as their constructed-input tests say, at a 100% line-coverage floor. | Every commit (pre-commit hook), every PR and merge-group commit (CI). | That a board actually produces the input these functions expect. That contract is proven separately, by a case's own acceptance runs on bench; `meta-wisekiosk/lib/oeqa`'s cases are transport only and are outside this tier's coverage population by construction. |
| Build (`just build`) | The kas config resolves and bitbake completes: an image artifact exists. | On demand, locally — never in CI, which does not build. | Whether the image differs from the last one, whether it boots, whether it serves anything. |
| Device smoke (`testimage` in the pipeline, or `just oe-test <target>` by hand) | The backend unit is active, `/healthz` answers, the page serves, WebKit still composites on the GPU, the page is still painting, and the page is applied as the application designs it — on **one** physical device, one boot. Both run the identical `meta-wisekiosk/lib/oeqa/runtime/cases/kiosk.py` suite and write the same run record. | The pipeline, once per queue job, after an OTA install (never a flash). By hand, any time, against any board `local/device-identity.md` names — never prod, which the suite's own hostname check refuses. | The shared boot partition (`config.txt`, `cmdline.txt`, `boot.scr`, and `uboot.env` apart from RAUC's own boot-selection variables) — an OTA writes only the slot rootfs it boots, which does carry the kernel. The RAUC slot layout, which an OTA never touches, or a second boot. |
| OTA/rollback (the queue run) | Install, reboot, and — for a queue run — mark-bad, reboot and land back on the baseline slot all completed, and the device answered again each time. | Every queue job. | Whether the slot rolled back *into* would itself survive a fresh install — it was booted back into, not reinstalled. There are only two slots. |

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
- `wisekiosk-pipeline/tree/local/keys` — a real, empty directory. The fleet signing key is bind-mounted
  read-only into the build container from the dev tree's own `local/keys` (`PIPELINE_KEYS_DIR` below);
  it is never copied, and the driver checkout, which never runs bitbake, gets no keys dir at all.
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

**The run record.** The suite's base class writes one record into `testresults.json`'s
`extraresults` before any case's own assertions run: `tool` (the checkout's own commit and dirty
state, and `argv`, identity-scrubbed), `board` (role, the live-hostname check, boot id, boot
ordinal since the booted slot's install, uptime, start/end), `image` (the booted slot's
`/etc/buildinfo` commit and slot), `app` (the served bundle's asset hashes, a keyed hash of
`config.json`, and its location-free summary), `sut` (the browser process, restart count, keyed
`kiosk.conf` hash, mode, kernel, cpufreq cap, timesync state), and one `page.<case id>` line per
DOM-probe case. No address, hostname, key material, coordinate or park identifier ever reaches it.
It lands wherever the harness writes `testresults.json` — under the driver at
`local/pipeline/runs/<sha>/testresults.json` for a pipeline job, under the path a hand run names
for `just oe-test`. `run.sh` reads it back before posting: a missing or malformed record, an
`image=` that is not `$SHA`, or `dirty=1`, is the job's own failure, never posted as a pass.
`report-build.py` renders the record's lines verbatim under their own heading, never as case rows,
so a later change to the record's shape needs no change to this renderer.

**The `/data` precondition.** Before every job, `run.sh` compares bench's `/data/config/kiosk.conf`
and `/data/config/config.json` keyed hashes against `just pipeline-accept-bench-config`'s last
recorded values, and refuses the job on any difference — a seed a prior run's own case left behind,
or a hand edit, is an environment problem a person accepts, not a silent comparison against a stale
baseline. `pipeline-accept-bench-config` needs the timer off; it prints both hashes and
`kiosk.conf`'s key names, never its values.

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

**Each queue job's buildhistory starts from the baseline tag.** Immediately before the job's own
build, `build/buildhistory` is reset to the job's base commit's tag, so the build's own
version-going-backwards check never compares against another candidate's leftover packages.

**Records** live at `local/pipeline/runs/<sha>/` under the driver: the build log, each OTA stage's
log, `testresults.json`, and the assembled report body.

**An infrastructure failure** — the device unreachable, the device's live hostname not matching the
recorded `PIPELINE_TARGET_HOSTNAME` (the address now reaches a different device), the shared
bitbake-hashserv not answering before a build, the job's base commit not resolving, a baseline build
failing, the rollback reboot never coming back, the rollback not landing back on the pre-install slot,
a report or status failing to post, or the process exiting for any other reason while the device sits
mid-OTA — writes `local/pipeline/DISABLED` under
the driver with the reason and disables the timer. Nothing loops silently. Fix the cause, then `just
pipeline-on` -- it prints the DISABLED reason and clears the file itself, as an explicit
acknowledgement, before re-enabling.

A job's own build, bundle, preflight, send or install failing, or the device not booting the new slot,
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

`just oe-test <target-ip>` runs the identical suite — `meta-wisekiosk/lib/oeqa/runtime/cases`, over
the shared `meta-wisekiosk/lib/wisekiosk` package — with `oe-test runtime`, no bitbake, no OTA,
against any board already built and booted. `tools/oe-test.sh` resolves `KIOSK_TARGET_ROLE` and
`KIOSK_TARGET_HOSTNAME` from `local/device-identity.md` (the role whose recorded address is
`<target-ip>`, and bench's own recorded hostname — the suite refuses any board that is not bench
regardless), refuses with a message if the HMAC key, the identity file, `sources/poky`, or the
last build's deploy artifacts are missing, and writes its own run record under gitignored
`local/oe-test/<timestamp>/`. It never touches RAUC, never installs, never reboots: only a case's
own stimulus (arming the DOM probe, stopping a service) changes anything on the board, and each
case restores what it changed.

## The render and applied cases

`test_render_advancing` captures the same default region `tools/kiosk-render-check.sh` already
uses — that script's own header has the geometry's rationale — and judges the two captures with
`wisekiosk.render.verdict`, a port of the script's own guards.

`test_page_applied` reads the page's state back through `document.title`, because surf's console
does not reach the journal on this image: the DOM probe writes its state there on every finished
load and every 5 s after, and the case reads it back over ssh with `xwininfo -tree` (surf sets
override-redirect, so its window carries no `_NET_*` properties and is absent from the client list)
and `xprop`'s `WM_NAME`, the same channel `kiosk-bootprof`'s `measure-surf.sh` already reads.
