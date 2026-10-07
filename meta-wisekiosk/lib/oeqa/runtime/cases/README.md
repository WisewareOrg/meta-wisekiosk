# meta-wisekiosk/lib/oeqa/runtime/cases

The oeqa suite bitbake and `tools/oe-test.sh` both run. [`docs/testing.md`](../../../../../docs/testing.md)
§"The hand-run path" has how the loader finds and selects a package here by name.

**One folder per device test, named for the test.** Each is a package:

- `case.py` — the `oeqa.runtime.case.OERuntimeTestCase` subclass; the only module in the package that
  imports `oeqa`.
- `verdict.py` or `record.py` — the package's own pure functions: strings and dicts in, a verdict or
  a record line out, no `self.target.run`, no `subprocess`, nothing that touches a device or the
  network.
- `tests/` — pytest over `verdict.py`/`record.py`, constructed inputs, every branch, held to a 100%
  line and branch coverage floor by `just test`. `case.py` is outside this population by
  construction: it imports `oeqa`, which is not on `sys.path` on the host `just test` runs on.

A case's own job is to move bytes and call its verdict: `self.target.run`/`copyTo` collects from the
device, the package's pure function judges what came back, and the case asserts on that judgement.
The case itself never parses or decides.

- `kiosk/` — the shared base, `WiseKioskCase`: the once-per-run record (role and hostname refusal,
  the boot/image/app/sut lines) every other package's case inherits, plus the parsers and R-line
  builders every one of them reads or writes through, in `record.py`.
- `kiosk_render/` — `test_render_advancing`, judged by `verdict.py`'s two-frame verdict.
- `kiosk_applied/` — `test_page_applied`, `probe.js` (the DOM probe surf evaluates; no recipe, the
  case deploys it with `copyTo`), and `verdict.py`'s title parser and verdict.
- `kiosk_backend_unit/`, `kiosk_healthz_bound/`, `kiosk_page_serves/`, `kiosk_health_flag/` — one
  pre-existing case apiece; no pure logic of their own to separate out, so no `verdict.py`/`record.py`
  and no `tests/`.

Every function here is certified against constructed or scrubbed board-captured inputs -- never an
invented device-output shape: the contract between what the device emits and what a function
expects is proven separately, by the case's own acceptance runs on bench.
