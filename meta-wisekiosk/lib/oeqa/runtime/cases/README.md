# meta-wisekiosk/lib/oeqa/runtime/cases

The oeqa suite bitbake and `tools/oe-test.sh` both run. [`docs/testing.md`](../../../../../docs/testing.md)
§"The hand-run path" has how the loader finds and selects a package here by name.

**One folder per test, named for the test.** Each is a package:

- `case.py`, and `selfcheck.py` where present — each an `oeqa.runtime.case.OERuntimeTestCase`
  subclass; the only modules in the package that import `oeqa`. `selfcheck.py` holds a hand-run
  self-test of the package's own checker (proof it can go red), one method named for what it
  exercises (e.g. `test_applied_detects_dead_url`), run on bench as
  `just oe-test <target-ip> kiosk_<name>.selfcheck` whenever that checker changes. Named in full,
  never the bare package name, in `includes/testimage.yaml`'s own `TEST_SUITES` —
  [`includes/testimage.yaml`](../../../../../includes/testimage.yaml) names why.
- `verdict.py` — the package's own pure functions: strings and dicts in, a verdict out, no
  `self.target.run`, no `subprocess`, nothing that touches a device or the network.
- `tests/` — pytest over `verdict.py`, constructed inputs, every branch, held to a 100% line and
  branch coverage floor by `just test`. `case.py` and `selfcheck.py` are outside this population by
  construction: both import `oeqa`, which is not on `sys.path` on the host `just test` runs on.

A case's own job is to move bytes and call its verdict: it collects (`self.target.run`/`copyTo` for
a device case, `debugfs`/a host subprocess for `kiosk_image`), the package's pure function judges
what came back, and the case asserts on that judgement. The case itself never parses or decides.

- `kiosk_render/` — `test_render_advancing`, judged by `verdict.py`'s two-frame verdict.
- `kiosk_applied/` — `test_page_applied`, `probe.js` (the DOM probe surf evaluates; no recipe, the
  case deploys it with `copyTo`), and `verdict.py`'s title parser and verdict. The one probe script
  every other probe-reading case below reads, never duplicates.
- `kiosk_layout/` — the appliance's own layout-floor need (`docs/requirements/srs/SRS007`), reading
  the mode `DISPLAY=:0 xrandr` reports directly, never through the probe.
- `kiosk_browser_restart/` — the appliance's own need that the browser comes back on its own when it
  dies (`docs/requirements/srs/SRS005`; unit supervision, `Restart=always`), judged by `verdict.py`'s
  own nonce comparison between the sample read before the kill and the samples read after.
- `kiosk_backend_unit/`, `kiosk_healthz_bound/`, `kiosk_page_serves/`, `kiosk_health_flag/` — one
  pre-existing case apiece; no pure logic of their own to separate out, so no `verdict.py` and no
  `tests/`.
- `kiosk_image/` — the image-content tier, reads the deployed `.ext4` through the build's own
  datastore, never a device. Subclasses `framework.base.ImageCase`, not `WiseKioskCase`, and writes
  no record line. Three methods: the display-launch unit's effective `ExecStart` carries its
  designed flags (`docs/requirements/srs/SRS008`, `docs/requirements/tst/TST008`); the display's
  served `index.html` is in the rootfs (`docs/requirements/srs/SRS009`,
  `docs/requirements/tst/TST009`); and the required binaries later checks need are present (a
  guard, no item of its own). The bundle-image hash tie is `tools/reproducibility-gate.sh`'s own
  job, not this package's.
- `kiosk_units/` — every unit `meta-wisekiosk`'s own recipes ship loads with its dependencies
  satisfied (`docs/requirements/tst/TST010`, child of `SRS008`): `systemd-analyze verify` on the
  board, one call per shipped unit, derived from the layer's own `recipes-*/**/*.service`/`*.timer`
  files rather than hand-kept. Runs on the board, the appliance's own systemd validating its own
  units, not a host-side artefact read; needs the `systemd-analyze` package, added to the image
  alongside its siblings in `kiosk-zero-w.yaml`'s own `IMAGE_INSTALL:append`.

**The shared base and record parsing are not a case, so they are not here.** Every device package's
`case.py` subclasses `WiseKioskCase` and reads or writes the run record through `record.py`
(`kiosk_image` subclasses `ImageCase` instead and writes no record), both in
[`../framework/`](../framework/README.md) — a library, not a test, made importable the way any other
layer's own oeqa extension is, by `layer.conf`'s `addpylib`, rather than discovered as a case.
`framework.base` holds the timing bounds shared across packages: `POLL_SECONDS` between poll
attempts, `POLL_ATTEMPT_TIMEOUT_SECONDS` for one remote command's round trip,
`RESTART_TIMEOUT_SECONDS` for a `systemctl restart kiosk.service` call, and `BOUND_SECONDS` for the
backend-unit and `/healthz` deadlines. A package's own deadline is named in that package.

Every function here is certified against constructed or scrubbed board-captured inputs -- never an
invented device-output shape: the contract between what the device emits and what a function
expects is proven separately, by the case's own acceptance runs on bench.
