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
`build` and `bundle` hooks, a host suite before anything is installed, then a target suite against the
booted board. The runner never touches the board itself:

```sh
bench test <ref>               # by hand: build, run both suites; the target suite installs on the board LG_ENV names
bench test <ref> --skip-build  # by hand: the target suite only, against the board as it is
bench run                      # on a timer: the merge queue's head entry, the same path
```

`--soak` (`bench test <ref> -- --soak`) gives TST014<!-- Memory over a long run --> its long period in place of the queue period and does not judge its growth bound; `bench run` never passes it.

`bench.toml`'s `[hooks]` carries a no-op `precondition` — the runner requires one; this layer's board
needs no state check before a run — `build` (`just build`) and `bundle` (`just kiosk-bundle`).
`[tests]` names the two suites:

- `tests/host_suite` — runs before anything is installed, against the build hook's own output. One
  test runs `tools/reproducibility-gate.sh --image` on the rootfs, so a candidate the gate refuses
  never reaches the board; the other unpacks the rootfs tarball and runs `systemd-analyze verify`
  and `systemctl is-enabled`, both `--root=`-pointed at it, against every unit this layer's recipes
  ship, so a unit that would strand the board never reaches it either.
- `tests/target_suite` — one autouse fixture (`conftest.py`) switches on `install_candidate`
  (`tests/conftest.py`'s shared setup) through `config_hashes_across_install`, which hashes the
  board's `config.json` before and after the install for TST019<!-- Configuration held across an image update -->
  and writes nothing. `install_candidate` installs the candidate on the board through
  `just kiosk-ota` and `just kiosk-reboot` when there is one, then reads the board's `/etc/buildinfo`
  over the ssh connection `Board` opens before the install and `Board.reboot` reconnects,
  printing its meta-wisekiosk commit into the run's own record on every run — so the record carries the board's commit even
  under a `-k`-filtered run where TST016<!-- Running the image update's build --> itself would not
  execute. The commit under test comes from the runner's own `bench_candidate` fixture, never an
  environment variable — `None` outside `bench test`/`bench run`, in which case the setup fixture
  skips only its install step, and TST016<!-- Running the image update's build --> and
  TST019<!-- Configuration held across an image update --> skip. TST016<!-- Running the image update's build -->
  reads the board's `/etc/buildinfo` itself and fails unless it names `bench_candidate`.
  The timezone test overlays `/etc` from `/run` while it runs and unmounts it at teardown.
  Installing the probe (`board.app.page.install_probe`) bind-mounts it from `/tmp` over surf's
  script path and restarts the browser so the test can read what the page shows; teardown unmounts
  it and restarts the browser again. Every test marked `sends_update` runs after every other test
  in the suite. The image-update tests build their bundles in the host's `/tmp`, which
  `tools/kas-run.sh` mounts through `KAS_RUN_TMP_DIR`.
  The device context (`device_context` in `conftest.py`) is recorded on every test. The
  refused-update tests build two small bundles through `tools/kas-run.sh`, so they need the
  checkout's own build tree and the signing keys the bench host's environment file names. The
  keyboard test builds evemu-tools through `tools/kas-run.sh` the same way, so it needs the build
  tree too, and while it runs the panel shows the board's text console. The frozen-page test
  swaps the board onto `clock-seconds.json` through `board.app.config.use` and stops the browser's
  web processes, and an undo registered on the board's cleanup resumes them. The backend-late test
  masks `wisekiosk.service` in `/run`, soft-reboots the board's userspace with the mask held, binds
  the probe without restarting the browser, and arms a board-side `systemd-run` timer that releases
  the backend should the host be lost; teardown releases it too. The backend-crash tests kill the
  backend, and the browser-start one first delays its restart with a `RestartSec` drop-in in
  `/run`, which teardown removes. All of these live in `/run`, so a real reboot clears any a dead
  run leaves, and `config_hashes_across_install` clears the backend's runtime drop-ins and mask at
  the start of every session.

Every install the target suite makes goes through [`tools/kiosk-install.sh`](../tools/kiosk-install.sh),
so the bench host needs Docker, a free port 80, and a board that reaches the host's port 80 at the
address the host's ssh session comes from. A plain LAN meets that, and so does WSL2 with Docker
Desktop, which publishes the port on the Windows side; NAT or an ssh jump between the board and the
host does not, and the install then fails to fetch the bundle.

`bench run` also reads `[github]` — the GitHub App that posts the `bench-pipeline` check run, and the
path to its private key on the bench host — and `[run]`, naming the systemd unit it disables on the
bench's own failure.

`--skip-build` runs the `precondition` hook and the target suite only — no `build`, no `bundle`, no
host suite, and `bench_candidate` stays `None` — so it tests a running board without a build and
installs nothing. `just bootprofile` runs this way, against `tests/diagnostics` — see
[the bootprof README](../meta-wisekiosk/recipes-core/kiosk-bootprof/README.md) for what that run
does. Whether such a run counts as evidence for a review or an investigation is
[WiseBenchManager's own rule](https://github.com/WisewareOrg/WiseBenchManager/blob/main/docs/decisions/0001-verify-with-a-python-bench-runner.md),
ADR 0001 rev 6 decision 9 (provenance), not this layer's.

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

A failure of the plug, or a board that answers in the same boot after the cut, ends the session as
the bench's failure rather than the candidate's, as
[WiseBenchManager's job](https://github.com/WisewareOrg/WiseBenchManager#the-job) tells the two
apart.

## How a target-suite test is written

**What every test needs comes from one place; what only some need is a fixture.** Before each test,
`pytest_runtest_setup` in `tests/target_suite/conftest.py` puts a new `Board` and the test's
`Record` on the test's instance. What only some tests need — the replay `proxy`, the
`candidate_bundles`, `refused_offers` and `evemu_helpers` builds, `pytestconfig`, `tmp_path` — is an
ordinary pytest fixture, taken as an argument by the test method that uses it.

**A test file holds four things:** its imports; its requirement values (bounds, stimulus values and
the test's own wait limits); its marks; and one class, `Test<Subject>(BoardTest)`. `BoardTest`
(`tests/target_suite/board_test.py`) only declares `board` and `record`. The class holds test methods
and, when every test in it starts from the same board state, a `setup_method` — gtest's `SetUp` —
which registers its undos on `self.board.cleanup` and takes no fixture. No class writes
`teardown_method`: it would run after the board's undo. Each test method reads arrange, act, assert,
three blocks separated by single blank lines, and records through `self.record(name=value, ...)`,
whose calls set the record's names, values and order.

**The board is a tree of parts** (`tests/board/`): `board.app` (`backend`, `config`, `page`),
`board.screen` (`display`, `captures`), `board.console` (`terminals`, `keyboard`), `board.system`
(`clock`, `timezone`, `memory`, `soak`), `board.network` (`outage`, `load`) and `board.updates`, with
the board-wide reads on `Board` itself. A part composes its sub-parts and does nothing else. A
sub-part is one small class in its own module that holds only the board and registers its undos on
`board.cleanup`; it reaches a sibling through the board's public path, never a private name (ruff's
SLF001 gates that). It never holds the record: a method that records takes `record` as an argument
— an `assert_…` that records before it fails, or a step whose evidence lands at teardown — and every
other method returns what it measured for the test to record. What a test measured before a
stimulus, the test holds. A read the test records beside its verdict returns the raw text with the
parse, and a read the test polls keeps its last good result. `tests/board/` imports nothing from
`tests/target_suite/` at run time, since the diagnostics import it without that directory on the
path; the host-side objects (`Record`, `ContainerDir`, the bundle and helper builds) live in
`tests/target_suite/`. The diagnostics get their own Board from a function-scoped `board` fixture in
`tests/diagnostics/conftest.py`, and the session fixtures each open one with `with Board(target)`.

**Teardown and record order.** For each test, in this order: the hook builds the Board and the
Record; the autouse fixtures run, and `device_context` records the device facts; `setup_method`
runs; the test's own fixtures start (the `proxy` records `recording_sha256`); the test runs;
`pytest_runtest_teardown` closes the Board's cleanup, last first, while the fixtures are still
alive; then the fixtures tear down (the `proxy` records `served_count` and `killed_count`, then
`device_context` records `end`). The teardown hook runs the undo in `try` and pytest's own teardown
in `finally: yield` — never `finally: return (yield)`, which would swallow a failing undo and pass
the test. A replay test's arrange block puts the backend behind the proxy, then installs the probe,
so its record reads device facts, `recording_sha256`, `probe_sha256`, then the test's own.

**Ordering.** `@pytest.mark.sends_update` on the image-update and refused-update classes is the only
ordering rule: `pytest_collection_modifyitems` runs the marked tests after every other.

**The lint gate.** [`tools/ci-guards.sh`](../tools/ci-guards.sh) guard 22 runs the repo `.venv`'s
pinned `ruff check` (the select in `pyproject.toml`), `ruff format --check`, `interrogate --fail-under
100` and `pydoclint` over every tracked `tests/*.py`; a missing tool fails the guard.
