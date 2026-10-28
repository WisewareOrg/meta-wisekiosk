# Testing

What proves a change is good enough to ship, at each tier, and — just as importantly — what a green
result at that tier does **not** let you conclude.

| Tier | Guarantees | Runs | What green does not say |
|---|---|---|---|
| Static (`just guards`, CI) | Repository invariants hold: no secret or identity reaches a tracked file, shell and YAML parse, every wiring self-test passes. | Every commit (pre-commit hook), every PR and merge-group commit (CI). | Anything about a Yocto build. This tier never invokes bitbake. |
| Build (`just build`) | The kas config resolves and bitbake completes: an image artifact exists. | On demand, locally — never in CI, which does not build. | Whether the image differs from the last one, whether it boots, whether it serves anything. |
| Host (`tests/host_suite`) | Both checks pass before any install: the rootfs is attributable to a clean, pushed commit, and every unit this layer's recipes ship is present, has an `ExecStart=` that resolves, and is enabled by name. | After the build, never under `bench test --skip-build`. | Whether a unit actually loads or fails at runtime, drop-in overrides, `ExecStartPre=`/`ExecStartPost=`/`ExecStop=`, or whether the resolved binary is executable. |
| Device smoke (`tests/target_suite`) | The board's `/etc/buildinfo` names the installed commit, the page is served, the page is served again within 60 s of a backend crash, and the instance's own HTTPS fetches, made through the proxy it is set to use, complete and are answered from a recording of its upstream, every recorded request at least once and none unanswered. | `bench run`, once per queue job. | The shared boot partition (`config.txt`, `cmdline.txt`, `boot.scr`, and `uboot.env` apart from RAUC's own boot-selection variables) — an OTA writes only the slot rootfs it boots, which does carry the kernel. The RAUC slot layout, which an OTA never touches, or a second boot. Whether the instance's traffic leaves the board, whether the board resolves its upstreams' names, or whether its system CA store verifies them: the recording is served by a proxy on the test host, reached through an SSH tunnel on the board's own loopback, which resolves names and presents certificates its own CA signs, and the backend trusts that CA alongside the store. |

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

`bench.toml`'s `[hooks]` carries a no-op `precondition` — the runner requires one; this layer's board
needs no state check before a run — `build` (`just build`) and `bundle` (`just kiosk-bundle`).
`[tests]` names the two suites:

- `tests/host_suite` — runs before anything is installed, against the build hook's own output. One
  test runs `tools/reproducibility-gate.sh --image` on the rootfs, so a candidate the gate refuses
  never reaches the board; the other runs `unit_files.py`'s `check_image` against every unit this
  layer's recipes ship, so a unit that would strand the board never reaches it either.
- `tests/target_suite` — its own session-scoped, autouse fixture (`conftest.py`) installs the
  candidate on the board through `just kiosk-ota` and `just kiosk-reboot` when there is one, then
  gets labgrid's SSHDriver fresh and reads the board's `/etc/buildinfo`, printing its meta-wisekiosk
  commit into the run's own record on every run — so the record carries the board's commit even
  under a `-k`-filtered run where TST016 itself would not execute. The commit under test comes from
  the runner's own `bench_candidate` fixture, never an environment variable — `None` outside
  `bench test`/`bench run`, in which case the setup fixture skips only its install step and TST016
  alone skips: it reads the board's `/etc/buildinfo` itself and fails unless it names
  `bench_candidate`.

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

The board comes from labgrid's own env file, pointed at with `LG_ENV` — a target named `main`, a
`NetworkService` resource carrying the board's address, an `SSHDriver` — kept untracked under
`local/`, since this repository is public and the address is site-specific.

On the bench host, `bench run`'s environment file sets `LG_ENV` and, for this layer,
`PIPELINE_KEYS_DIR`.
