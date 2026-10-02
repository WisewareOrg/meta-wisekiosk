# Testing

What proves a change is good enough to ship, at each tier, and — just as importantly — what a green
result at that tier does **not** let you conclude.

| Tier | Guarantees | Runs | What green does not say |
|---|---|---|---|
| Static (`just guards`, CI) | Repository invariants hold: no secret or identity reaches a tracked file, shell and YAML parse, every wiring self-test passes. | Every commit (pre-commit hook), every PR (CI). | Anything about a Yocto build. This tier never invokes bitbake. |
| Build (`just build`) | The kas config resolves and bitbake completes: an image artifact exists. | On demand, locally — never in CI, which does not build. | Whether the image differs from the last one, whether it boots, whether it serves anything. |
| Artifact delta (`just artifact-diff`; size-blind) | Whether package versions, the file list, or file metadata (mode/owner/size/path) changed between two builds sharing one buildhistory-enabled build directory. An empty delta is itself a pass: the pipeline posts success and runs no OTA, `testimage` or rollback for it. | After two `just build` runs. | Content. Buildhistory records path/mode/owner/size, not bytes — a same-size content edit reads as "no change". |
| Device smoke (`testimage` + stages) | The backend unit is active, `/healthz` answers, the page serves, WebKit still composites on the GPU, the page is still painting — on **one** physical device (the one named in the gitignored `local/device-identity.md`, [`CONTRIBUTING.md`](../CONTRIBUTING.md) §"Before you change anything"), **one** boot, after an OTA install (never a flash). | The pipeline, once per run. | Any boot file (kernel, `config.txt`, `cmdline.txt`, device tree) — the pipeline writes none of them — the RAUC slot layout, which an OTA never touches, or a second boot. |
| OTA/rollback (the queue run) | Install, reboot, and — for a queue run — mark-bad, reboot and land back on the baseline slot all completed, and the device answered again each time. | Every queue run whose artifact delta is non-empty. | Whether the slot rolled back *into* would itself survive a fresh install — it was booted back into, not reinstalled. There are only two slots. Whether this tier ran at all — a queue run with an empty delta posts success without it. |

## Running it

```sh
just pipeline-install                # once per host, idempotent -- reads $PIPELINE_DRIVER_REF,
                                      # $DL_DIR, $SSTATE_DIR, $PIPELINE_TARGET
just pipeline-on                     # enable the timer
just pipeline-off                    # disable it
just pipeline-status                 # timer state + any DISABLED reason
just pipeline-run                    # one job by hand: the queue head, or a missing baseline
```

The job is the head of the merge queue — the entry whose own base commit is `origin/main`'s current
tip, since every later entry is built on an earlier one's still-speculative result, not on main — and
a PR enters the queue after its static checks pass and merges only if `bench-pipeline` is green on its
merge-group commit. A lone queue ref whose own base is not that tip is stale — GitHub rebuilds it —
and reads as no job, the same as an empty queue.

`pipeline-install` is the whole reprovisioning procedure — nothing is done to a host by hand that it
does not also do. It creates, all under `$HOME`:

- `wisekiosk-pipeline/driver` — this repository, checked out at `driver_ref`; runs `run.sh`.
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
  also pushes to GitHub.
- `wisekiosk-pipeline/tree/build/cache/hashserv.db` — seeded from the dev tree's own hash-equivalence
  database (never overwritten once the pipeline has built its own), so a fresh build dir's unihash
  lookups hit the shared `SSTATE_DIR` instead of missing and rebuilding from scratch.
- `.config/systemd/user/wisekiosk-pipeline.{service,timer}` — symlinks to this repository's copies.

It does **not** enable the timer — `pipeline-on` is the separate, deliberate step.

**The device under test, and the shared `downloads/`/`sstate-cache/`, are reserved while the timer is
on.** A hand `just build` or a manual OTA while `pipeline-on` races the pipeline's own run; `just
pipeline-off` first. The pipeline's own `build/` (TMPDIR) is not shared, so it alone never conflicts
with a hand build.

**An empty artifact delta is a pass.** A queue run whose delta comes back empty posts success and
stops there — no bundle, OTA, `testimage` or rollback runs for it.

**A baseline run never touches the device.** It builds the missing commit, tags its buildhistory, and
stops — no status is posted and no PR comment is written, because no job's own commit is under test.
The next tick picks up the queue job against the now-tagged baseline.

**Records** live at `local/pipeline/runs/<sha>/` under the driver: the build log, the artifact delta,
each OTA stage's log, `testresults.json`, and the assembled report body.

**An infrastructure failure** — the device unreachable, the device's live hostname not matching the
recorded `PIPELINE_TARGET_HOSTNAME` (the address now reaches a different device), a baseline build
failing, the baseline ref or its buildhistory tag not resolvable, the rollback reboot never coming
back, the rollback not landing back on the pre-install slot, a report or status failing to post, or
the process exiting for any other reason while the device sits mid-OTA — writes `local/pipeline/DISABLED` under
the driver with the reason and disables the timer. Nothing loops silently. Fix the cause, then `just
pipeline-on` -- it prints the DISABLED reason and clears the file itself, as an explicit
acknowledgement, before re-enabling.

A job's own build, bundle, preflight, send or install failing, or the device not booting the new slot,
is not an infrastructure failure: it posts `failure` on the job's commit and a PR comment with the
failing logs, and the timer stays on for the next job.

`PIPELINE_TARGET` or `PIPELINE_TARGET_HOSTNAME` unset refuses the run outright (rc 2) without
touching the timer — a `pipeline.env` configuration problem, like any other required variable
missing, not an infrastructure failure. More than one merge-queue ref based on `origin/main`'s tip
refuses the same way (rc 2, timer untouched): the ambiguity is visible only in the timer's own log,
with no DISABLED file and no PR comment.

A new host needs a clone, the dev tree's `local/device-identity.md`, `gh auth login`, and
`just pipeline-install`.
