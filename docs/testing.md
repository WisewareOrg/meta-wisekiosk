# Testing

What proves a change is good enough to ship, at each tier.

| Tier | Guarantees | Runs |
|---|---|---|
| Static (`just guards`, CI) | Repository invariants hold: no secret or identity reaches a tracked file, shell and YAML parse, every wiring self-test passes. | Every commit (pre-commit hook), every PR and merge-group commit (CI). |
| Build (`just build`) | The kas config resolves and bitbake completes: an image artifact exists. | On demand, locally — never in CI, which does not build. |
| Host (`tests/host_suite`) | Both checks pass before any install: the rootfs is attributable to a clean, pushed commit, and `systemd-analyze verify`/`systemctl is-enabled`, run against the unpacked rootfs, are clean for every unit this layer's recipes ship. | After the build, never under `bench test --skip-build`. |
| Device smoke (`tests/target_suite`) | The candidate, installed on the bench board by an image update, passes every active `TST` item whose check is in `tests/target_suite`. Each item in the [requirements tree](requirements/README.md) states its own stimulus and pass condition. | `bench run`, once per queue job. |

## Running it

[WiseBenchManager](https://github.com/WisewareOrg/WiseBenchManager) is a separate, generic
hardware-in-the-loop runner, cloned and built outside this tree per its own README. Pointed at this
checkout, it reads the tracked `bench.toml` here — which never names a machine or a board — runs its
`build` and `bundle` hooks, a host suite before anything is installed, then a target suite against
the booted board. Builds on one host take turns ([`image.md`](image.md) §"Building"). The
runner never touches the board itself:

```sh
bench test <ref>               # by hand: build, run both suites; the target suite installs on the board LG_ENV names
bench test <ref> --skip-build  # by hand: the target suite only, against the board as it is
bench run                      # on a timer: the merge queue's head entry, the same path
```

`--soak` (`bench test <ref> -- --soak`) adds a day-long run of TST014<!-- Memory over a long run --> on top of its queue-period run, and does not judge that run's growth bound; `bench run` never passes it.

`bench.toml`'s `[hooks]` carries `precondition`, which installs the packages the test helpers import,
`build` (`just build`) and `bundle` (`just kiosk-bundle`).
`[tests]` names the two suites:

- `tests/host_suite` — runs before anything is installed, against the build hook's own output. One
  test runs `tools/reproducibility-gate.sh --image` on the rootfs, so a candidate the gate refuses
  never reaches the board; the other unpacks the rootfs tarball and runs `systemd-analyze verify`
  and `systemctl is-enabled`, both `--root=`-pointed at it, against every unit this layer's recipes
  ship, so a unit that would strand the board never reaches it either.
- `tests/target_suite` — one autouse fixture (`conftest.py`) switches on `install_candidate`
  (`tests/conftest.py`'s shared setup, whose docstring gives its steps). It installs the candidate
  through `just kiosk-ota` when there is one, and what it found before and after is the `Installed`
  that TST016<!-- Running the image update's build -->,
  TST019<!-- Configuration held across an image update --> and
  TST028<!-- Log kept across an image update --> judge, as `board.updates.installed`. It prints the
  board's meta-wisekiosk commit into the run's own record on every run — so the record carries the
  board's commit even under a `-k`-filtered run where TST016<!-- Running the image update's build -->
  itself would not execute. The commit under test
  comes from the runner's own `bench_candidate` fixture, never an environment variable — `None`
  outside `bench test`/`bench run`, in which case the setup fixture skips only its install, and the
  tests that judge it skip.
  What a test changes on the board, and how it is undone, is in the docstring of the `tests/board/`
  method that changes it. Apart from an image update's slots, which the test returns to the
  candidate, each change lives in `/run` or `/tmp`, so a real reboot clears any a dead run leaves,
  and `install_candidate` clears the backend's runtime drop-ins and mask at the start of every
  session. While the keyboard test runs, the panel shows the board's text console.

The target suite builds its test bundles and the virtual mouse's and keyboard's evemu-tools in the
kas container through `tools/kas-run.sh`, so the bench needs the checkout's own build tree, and the
signing keys the bench host's environment file names. The refused-update tests' bundles and
evemu-tools are built under `build/`. The image-update tests' bundles are built in the host's `/tmp`, which
`tools/kas-run.sh` mounts through `KAS_RUN_TMP_DIR`: they are signed by the operator key and carry
the fleet's `compatible`, so they are kept only in memory (the host's `/tmp`, and the bundle
server's memory for the length of an install), never in the build tree's deploy output (#252 image
update behaviour). Before installing one, `Updates.allow_test_bundle` confirms the board refuses it
without the run's nonce.

Every install the target suite makes goes through [`tools/kiosk-install.sh`](../tools/kiosk-install.sh),
so the bench host needs what any installing host needs ([`updates.md`](updates.md) §"Delivering an
update"); an install that cannot reach the host's server fails to fetch the bundle.

`bench run` also reads `[github]` — the GitHub App that posts the `bench-pipeline` check run, and the
path to its private key on the bench host — and `[run]`, naming the systemd unit it disables on the
bench's own failure.

`--skip-build` runs the `precondition` hook and the target suite only — no `build`, no `bundle`, no
host suite, and `bench_candidate` stays `None` — so it tests a running board without a build and
installs nothing. `just bootprofile` runs this way, against `tests/diagnostics` — see
[the bootprof README](../meta-wisekiosk/recipes-core/kiosk-bootprof/README.md) for what that run
does. Whether such a run counts as evidence for a review or an investigation is
[WiseBenchManager's own rule](https://github.com/WisewareOrg/WiseBenchManager/blob/main/README.md#two-commands),
not this layer's.

Every dedicated test on a board is a pytest case under `tests/`, run through the bench driver as
`bench test <ref> -- <suite> -k <name>` — never an ad hoc script, loop or ssh one-liner. A test
driven outside the driver carries none of its provenance, and its result is not evidence for a
review, an investigation or a PR. By hand, a board is for inspection only: reading its state and
running read-only diagnostics.

`tests/diagnostics` also holds the check that a reset mid-install is caught: `bench test <ref> --
tests/diagnostics -k install_reset_capture -rP` installs the candidate, then runs a second `just
kiosk-ota` and crashes the board once rauc reports writing the slot, and passes only when that
install's own output carries the reset and the board's pstore read back after it. It crashes the
board on purpose, so it runs only by hand, never in the queue job.

`tests/diagnostics -k fallback_probe` is the safe check of the slot fallback before any install meant
to fail: it installs a good copy of the candidate in the slot not booted, zeroes that slot's boot
attempts and restarts, and passes only when U-Boot boots the other slot. Both slots stay bootable, so
it strands nothing.

`tests/diagnostics -k radio_under_load` reads the board's radio before and after the network load
TST008<!-- Sustained network load --> applies, and records the load's rate, the signal at each edge
and the counters' deltas across the load; it judges nothing. It changes nothing on the board, so it
runs with `--skip-build` against a running board.

`tests/applications/screenshot` is the suite of the screenshot application, which runs on the board.
It is separate from the image suite and the diagnostics, and the queue job does not run it.
`test_decoder.py`, on constructed buffers and no board, runs in `just guards` and CI. `bench test
<ref> -- tests/applications/screenshot -k on_board -rP` installs the candidate and runs
`test_on_board.py`; without the `-k`, the runner also runs `tests/target_suite`.

The board comes from labgrid's own env file, pointed at with `LG_ENV` — a target named `main`, a
`NetworkService` resource carrying the board's address, an `SSHDriver` — kept untracked under
`local/`, since this repository is public and the address is site-specific.

On the bench host, `bench run`'s environment file sets `LG_ENV` and, for this layer,
`PIPELINE_KEYS_DIR`.

The power-cut tests also need an `ExternalPowerDriver` in that file, whose commands run
`uv run --locked --env-file <file> kasa --host <plug> on` and `off` from the checkout, with the
plug's login in a `KEY=value` file outside the tree, passed by `--env-file` and never shell-sourced.
The `python-kasa` git pin in `pyproject.toml` is for that plug's login, and `renovate.json` records
why it is pinned.

The suites run in the runner's own environment. What the test helpers import and that environment
lacks is in `pyproject.toml`'s `tests` group, locked in `uv.lock`. `bench.toml`'s `precondition` hook
installs that group into `build/test-packages`, and pytest's `pythonpath` setting makes it
importable. The directory holds only that group, so it replaces no package of the runner's. `kasa` is
not imported: labgrid runs it as the plug's command.

A failure of the plug, or a board that answers in the same boot after the cut, ends the session as
the bench's failure rather than the candidate's, as
[WiseBenchManager's job](https://github.com/WisewareOrg/WiseBenchManager#the-job) tells the two
apart.

How a target-suite test is written is a contributor convention: [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
§"Writing a target-suite test".
