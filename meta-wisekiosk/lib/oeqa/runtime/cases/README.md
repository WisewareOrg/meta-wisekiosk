# meta-wisekiosk/lib/oeqa/runtime/cases

The oeqa suite bitbake and `tools/oe-test.sh` both run. [`docs/testing.md`](../../../../../docs/testing.md)
§"The hand-run path" has how the loader finds and selects a package here by name.

**One folder per device test, named for the test.** Each is a package:

- `case.py` — the `oeqa.runtime.case.OERuntimeTestCase` subclass; the only module in the package that
  imports `oeqa`.
- `verdict.py` — the package's own pure functions: strings and dicts in, a verdict out, no
  `self.target.run`, no `subprocess`, nothing that touches a device or the network.
- `tests/` — pytest over `verdict.py`, constructed inputs, every branch, held to a 100% line and
  branch coverage floor by `just test`. `case.py` is outside this population by construction: it
  imports `oeqa`, which is not on `sys.path` on the host `just test` runs on.

A case's own job is to move bytes and call its verdict: `self.target.run`/`copyTo` collects from the
device, the package's pure function judges what came back, and the case asserts on that judgement.
The case itself never parses or decides.

- `kiosk_render/` — `test_render_advancing`, judged by `verdict.py`'s two-frame verdict.
- `kiosk_applied/` — `test_page_applied`, `probe.js` (the DOM probe surf evaluates; no recipe, the
  case deploys it with `copyTo`), and `verdict.py`'s title parser and verdict. The one probe script
  every other probe-reading case below reads, never duplicates.
- `kiosk_backend_unreachable/`, `kiosk_recovery/`, `kiosk_config_errors/`, `kiosk_layout/` — the
  appliance's own fault, recovery, configuration and layout needs (`docs/requirements/srs/`
  `SRS003`-`SRS007`), each reading the same probe through `framework.probe`'s `title_lines`/`fields`
  and `WiseKioskCase`'s `arm_probe`/`titles`/`wait_applied`/`stop_backend`/`start_backend`, never a
  second probe or a copy of the walk.
- `kiosk_browser_restart/` — the browser's own recovery from being killed; no pure parsing of its
  own (it reads `kiosk_applied.verdict`'s), so no `verdict.py`.
- `kiosk_backend_unit/`, `kiosk_healthz_bound/`, `kiosk_page_serves/`, `kiosk_health_flag/` — one
  pre-existing case apiece; no pure logic of their own to separate out, so no `verdict.py` and no
  `tests/`.

**A `verdict.py` field extractor is deliberately non-validating.** `kiosk_config_errors`'s
`parse_configuration_error` and `kiosk_backend_unreachable`/`kiosk_layout`'s own field parsers
return whatever the probe's title carries verbatim, never checked against a known set of values --
the frontend decides what a field means; the extractor only reads it back. Catching a genuinely
wrong value is the seeded-fail run's own job (`kiosk_config_errors.test_configuration_errors`'
three seeds, `kiosk_layout.test_layout_seeded_fail`), not the extractor's.

**The shared base and record parsing are not a case, so they are not here.** Every package's
`case.py` subclasses `WiseKioskCase` and reads or writes the run record through `record.py`, both in
[`../framework/`](../framework/README.md) — a library, not a test, made importable the way any other
layer's own oeqa extension is, by `layer.conf`'s `addpylib`, rather than discovered as a case.

Every function here is certified against constructed or scrubbed board-captured inputs -- never an
invented device-output shape: the contract between what the device emits and what a function
expects is proven separately, by the case's own acceptance runs on bench.
