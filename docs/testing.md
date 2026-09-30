# Testing

What proves a change is good enough to ship, at each tier, and — just as importantly — what a green
result at that tier does **not** let you conclude.

| Tier | Guarantees | Runs | What green does not say |
|---|---|---|---|
| Static (`just guards`, CI) | Repository invariants hold: no secret or identity reaches a tracked file, shell and YAML parse, every wiring self-test passes. | Every commit (pre-commit hook), every PR (CI). | Anything about a Yocto build. This tier never invokes bitbake. |
| Build (`just build`) | The kas config resolves and bitbake completes: an image artifact exists. | On demand, locally — never in CI, which does not build. | Whether the image differs from the last one, whether it boots, whether it serves anything. |
| Artifact delta (`just artifact-diff`; size-blind) | Whether package versions, the file list, or file metadata (mode/owner/size/path) changed between two builds sharing one buildhistory-enabled build directory. | After two `just build-with-history` runs. | Content. Buildhistory records path/mode/owner/size, not bytes — a same-size content edit reads as "no change". |
| Bench smoke (`testimage` + stages) | The backend unit is active, `/healthz` answers, the page serves, WebKit still composites on the GPU, the page is still painting — on **one** physical board, **one** boot, after an OTA install (never a flash). | The bench pipeline, once per candidate. | Anything about `/boot` (kernel, U-Boot, the RAUC slot layout — an OTA never touches it), a second boot, or the **prod** board specifically. |
| OTA/rollback (the `pr` run) | Install, reboot, and — for a `pr` run — mark-bad, reboot and land back on the baseline slot all completed, and the board answered again each time. | Every `pr` candidate. | Whether the slot rolled back *into* would itself survive a fresh install — it was booted back into, not reinstalled. There are only two slots. |
| Soak (prod, `kiosk-soak`) | The **prod** board's long-run memory and process health, read with `just soak-summary`. | Continuously, on the one board that carries it. | Anything about a candidate build — soak only ever watches whatever image prod is currently running, never a PR's. |

Three limits worth restating because they are easy to read past in the table: the artifact-delta tier
is **size-blind** by design — a same-size content change is invisible to it. The bench-smoke and
OTA/rollback tiers run **one boot on one bench board** — nothing here proves a second boot, a cold
boot, or the prod board's own behaviour, and nothing here ever touches `/boot` (kernel, U-Boot, the
RAUC slot layout), which stays unproven by every tier above soak.

## Running it

```sh
just pipeline-install                # once per host, idempotent -- reads $PIPELINE_DRIVER_REF,
                                      # $PIPELINE_BASELINE_REF, $DL_DIR, $SSTATE_DIR
just pipeline-on                     # enable the timer
just pipeline-off                    # disable it
just pipeline-status                 # timer state + any DISABLED reason
just pipeline-run                    # one job by hand: the next candidate
just pipeline-run baseline [sha]     # one job by hand: a baseline run
just pipeline-run pr <N>             # one job by hand: a PR's head
```

`pipeline-install` is the whole reprovisioning procedure — nothing is done to a host by hand that it
does not also do. It creates, all under `$HOME`:

- `wisekiosk-pipeline/driver` — this repository, checked out at `driver_ref`; runs `run.sh`.
- `wisekiosk-pipeline/tree` — a second, detached checkout of the same repository; the tree under test.
- `wisekiosk-pipeline/{driver,tree}/local/device-identity.md` — symlinks to the dev tree's own copy.
  One source of truth: a board swap updates one file.
- `wisekiosk-pipeline/{driver,tree}/local/keys` — symlinks to the dev tree's own `local/keys`, so
  `kiosk-zero-w.yaml`'s `AUTONOMOS_RAUC_*` paths (which resolve relative to the tree being built)
  find the fleet signing key without it ever being copied.
- `.config/wisekiosk/pipeline.env` — `PIPELINE_DRIVER`, `PIPELINE_TREE`, `PIPELINE_BASELINE_REF`
  (default `origin/main`), `PIPELINE_SSH_DIR`, the installing shell's own `PATH`, and two caches,
  overridable at install time: `DL_DIR` and `SSTATE_DIR` (default this repository's own
  `build/downloads` and `build/sstate-cache`, shared read-write with the dev tree's ordinary builds to
  avoid refetching or recompiling what is already there). The build dir itself is not recorded here:
  `run.sh` and `candidates.py` both derive it as `$PIPELINE_TREE/build` — kas's own default for that
  checkout — since it is never independently correct to set it to anything else.

  The build dir is never set as `KAS_BUILD_DIR`, and `run.sh` unsets any ambient one before running.
  Doing so moves bitbake's own `TMPDIR` to a different container mount point (`/build` instead of
  kas's default `/work/build`) — every recipe that resolves a path relative to `TOPDIR`, including
  `rauc-conf`'s search for the fleet signing key under `../local/keys`, then looks in the wrong place,
  and bitbake's own sanity checker refuses a build directory whose recorded `TMPDIR` does not match
  what it computes on the next run.
- `.config/wisekiosk/pipeline-ssh/` — a new ed25519 keypair, installed on bench's `authorized_keys`;
  `config`; `known_hosts`. Used only inside the `testimage` stage's container — never `~/.ssh`, which
  also pushes to GitHub.
- `.config/systemd/user/wisekiosk-pipeline.{service,timer}` — symlinks to this repository's copies.

It does **not** enable the timer — `pipeline-on` is the separate, deliberate step.

**Bench, and the shared `downloads/`/`sstate-cache/`, are reserved while the timer is on.** A hand
`just build` or a manual OTA while `pipeline-on` races the pipeline's own run; `just pipeline-off`
first. The pipeline's own `build/` (TMPDIR) is not shared, so it alone never conflicts with a hand
build.

Install, `rauc status mark-good` and `mark-bad` write only RAUC's own boot-selection variables in
`uboot.env`, exactly as every OTA does. No boot file -- kernel, DTB, `config.txt`, U-Boot itself -- is
ever written; that is `/boot`'s own gap, stated in the bench-smoke row above. The `/boot`-class header
also applies when a candidate moves poky's own pin, since U-Boot's recipe is poky's.

**Records** live at `local/pipeline/runs/<sha>/` under the driver: the build log, the artifact delta,
every stage's log, each stage's `testresults.json`, and the assembled (redacted, capped) report body.
The newest 20 run directories are kept; older ones are pruned automatically.

**An infrastructure failure** — bench unreachable, the build directory locked, a kas container already
running, the baseline ref or its buildhistory tag not resolvable, bench not resting on a tagged
baseline image, bench's hostname not matching the map, a reboot that never comes back, or the process
exiting for any other reason while bench sits mid-OTA — writes `local/pipeline/DISABLED` under the
driver with the reason and disables the timer. Nothing loops silently. Read the file, fix the cause,
and `just pipeline-on` again.

A new host needs a clone, the dev tree's `local/device-identity.md`, `gh auth login`, and
`just pipeline-install`.
