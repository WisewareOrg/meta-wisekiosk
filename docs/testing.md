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

`--soak` (`bench test <ref> -- --soak`) adds a day-long run of TST014<!-- Memory over a long run --> on top of its queue-period run, and does not judge that run's growth bound; `bench run` never passes it.

`bench.toml`'s `[hooks]` carries a no-op `precondition` — the runner requires one; this layer's board
needs no state check before a run — `build` (`just build`) and `bundle` (`just kiosk-bundle`).
`[tests]` names the two suites:

- `tests/host_suite` — runs before anything is installed, against the build hook's own output. One
  test runs `tools/reproducibility-gate.sh --image` on the rootfs, so a candidate the gate refuses
  never reaches the board; the other unpacks the rootfs tarball and runs `systemd-analyze verify`
  and `systemctl is-enabled`, both `--root=`-pointed at it, against every unit this layer's recipes
  ship, so a unit that would strand the board never reaches it either.
- `tests/target_suite` — one autouse fixture (`conftest.py`) switches on `install_candidate`
  (`tests/conftest.py`'s shared setup). It clears what a dead run left in `/run`, then, when there is
  a candidate, reads the board's `config.json` hash, writes a marker to the board's log, installs the
  candidate through `just kiosk-ota`, restarts the board (`Board.restart`), and reads the hash again;
  what it found is the `Installed` that TST016<!-- Running the image update's build -->,
  TST019<!-- Configuration held across an image update --> and
  TST028<!-- Log kept across an image update --> judge, as `board.updates.installed`. It then reads
  the board's `/etc/buildinfo` and prints its meta-wisekiosk commit into the run's own record on
  every run — so the record carries the board's commit even under a `-k`-filtered run where
  TST016<!-- Running the image update's build --> itself would not execute. The commit under test
  comes from the runner's own `bench_candidate` fixture, never an environment variable — `None`
  outside `bench test`/`bench run`, in which case the setup fixture skips only its install, and the
  three tests that judge it skip.
  The timezone test overlays `/etc` from `/run` while it runs and unmounts it at teardown.
  Installing the probe (`board.app.install_probe`) bind-mounts it from `/tmp` over surf's
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
  backend, and the browser-start one first holds back its restart with a `RestartSec` drop-in in
  `/run`, then restarts it itself; teardown removes the drop-in. All of these live in `/run`, so a
  real reboot clears any a dead run leaves, and `install_candidate` clears the backend's runtime
  drop-ins and mask at the start of every session.

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

**A test's contract is its item's text.** Each target-suite test checks one `TST` item in
[`docs/requirements/tst/`](requirements/tst/): the stimulus it states, its bound, and its pass, fail
and invalid conditions. Nothing else is part of the contract. A test records `requirement`, the
values its item judges, under the same names as every test of its kind (a recovery records
`back_s`), and what tells its case or its stimulus apart, or explains a failure the judged values
cannot. A check the item does not ask for is not in the test.

**Every test reads arrange, act, assert,** three blocks separated by single blank lines, against
`self.board` and `self.record`. A test method takes only `self` and its parametrized values: before
each test, `pytest_runtest_setup` in `tests/target_suite/conftest.py` puts a new `Board` and the
test's `Record` on the instance, and the board reaches what the run builds on demand through
`board.fixture(name)` — the update bundles as `board.updates.bundles`, the refused offers as
`board.updates.refused_offers`, the start-of-run install as `board.updates.installed`, the keyboard's
evemu build, and the replay proxy that `@replaying(<recording>)` (`board_test.py`) puts on a test.
A class holds test methods and, when every test in it starts from the same board state, a
`setup_method`; no class writes `teardown_method`, which would run after the board's undo.

**Tests that differ only in stimulus and bound are one parametrized test.** Each row is
`case(<TST id>, <values>…)`, which makes the item's id the case's id and its first value. A
fault-to-back test's row is the item, its fault, the read that says the thing is back, and its
bound: the fault returns the host instant its time counts from (or, where only the board knows it,
what reads that instant once the board answers), and `board.seconds_until(<read>, since=…)` times
from it. Instants are the host's `time.monotonic()`, taken on the side of the event that can only
overstate a time.

**A stimulus that did not take fails the check as invalid, from inside the stimulus.** A method that
applies a stimulus confirms it took and raises through `invalid_if(<how it did not take>)`
(`tests/board/part.py`), so the message reads `INVALID CHECK, not an appliance failure: …` and the
test body holds no validity logic of its own. Where the stimulus was applied and only its strength
or the board's starting state is in doubt, a `confirm_…` call ends the assert block instead, so an
observed breach fails first: TST008<!-- Sustained network load -->'s load, and the configuration
tests' loss check. A stimulus that did not take is judged invalid from inside it, before its outcome
is read, and so is one whose invalid condition can itself cause the breach, as a page reload makes
frame stalls.

**A test holds what it measured before the stimulus,** in a name that says so, and compares the
after against it.

**The board is a tree of parts** (`tests/board/`). `Board` itself is the connection: one
`run(cmd, check=, timeout=, retry_for=)`, file and port transfer, the undo-registering primitives
(`bind_over`, `run_later`, `unmount_if_mounted`), the restarts, the crash and the power cut, the
waits, and `fixture`. Everything else belongs to a part, each a subclass of `Part` built by
`Board.__init__` as `<Part>(self)`: `board.app` (its `backend`, `browser` and `config`),
`board.screen`, `board.console`, `board.system` (its `memory`), `board.network` (its `outage`) and
`board.updates`. Generic concepts are their own classes: a systemd `Unit` (`tests/board/unit.py`)
and a `Process` by name (`tests/board/process.py`). A part registers its undos on `board.cleanup`
and reaches a sibling only through the board's public path (ruff's SLF001 gates that). A part never
holds the record: every method returns what it measured, and the test records it. A recorded read
returns its raw text, with the parse where a record needs it. A named result type exists only where
the value is passed whole, carries methods, or has neighbouring fields of one type that a reorder
could silently swap. `tests/board/` imports nothing from `tests/target_suite/` at run time.

**Waits are tenacity polls.** `board.seconds_until(<read>, since=, reads=)` reads about once a second
until the read holds on `reads` reads in a row, counts each read at its end, and fails the test,
naming the read, once `Board.GIVE_UP_SECONDS` have passed; `board.longest_lapse_s(<read>, over=)`
reads for a span and returns the longest stretch it did not hold. A read that raises one of
`Board.ERRORS` does not hold. A polled read keeps its last good result for its caller, as
`board.app.last_sample` keeps the probe's last report.

**Teardown and record order.** For each test, in this order: the hook builds the Board and the
Record; the autouse fixtures run, and `device_context` records the device facts; `setup_method`
runs; the test's own fixtures start (the `proxy` records `recording_sha256`); the test runs;
`pytest_runtest_teardown` closes the Board's cleanup, last first, while the fixtures are still
alive; then the fixtures tear down (the `proxy` records `served_count` and `killed_count`, then
`device_context` records `end`). The teardown hook runs the undo in `try` and pytest's own teardown
in `finally: yield` — never `finally: return (yield)`, which would swallow a failing undo and pass
the test.

**Ordering and selection.** `@pytest.mark.sends_update` is the only ordering rule:
`pytest_collection_modifyitems` runs the marked tests after every other. A case marked
`@pytest.mark.soak` is deselected unless the run passes `--soak`.

**The lint gate.** [`tools/ci-guards.sh`](../tools/ci-guards.sh) guard 22 runs the repo `.venv`'s
pinned `ruff check` (the select in `pyproject.toml`), `ruff format --check`, `interrogate --fail-under
100` and `pydoclint` over every tracked `tests/*.py`; a missing tool fails the guard.
