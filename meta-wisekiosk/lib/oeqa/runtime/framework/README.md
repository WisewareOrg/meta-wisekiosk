# meta-wisekiosk/lib/oeqa/runtime/framework

The shared base every device test in [`../cases/`](../cases/README.md) builds on — a library, not a
test, so it is not discovered as one. Made importable as bare `framework` by `layer.conf`'s
`addpylib ${LAYERDIR}/lib/oeqa/runtime framework`;
[`docs/testing.md`](../../../../../docs/testing.md) §"The hand-run path" has the mechanism and the
two import conventions it requires.

- `base.py` — `WiseKioskCase`, the once-per-run record (role and hostname refusal, the boot/image/
  app/sut lines) every device case inherits, plus `titles()` (the one window-title walk every
  probe-reading case shares). `kiosk_image`, the host-only image-content tier, needs none of this
  (it never touches a board) and subclasses `oeqa.runtime.case.OERuntimeTestCase` directly in its
  own `case.py` instead. Imports `oeqa`, like a `case.py`, so it is outside `just test`'s coverage
  population the same way.
- `record.py` — the run record's own parsers, scrubbers and R-line builders, plus
  `hostname_mismatch`, which builds the refusal message from the observed and recorded hostnames.
  Pure: no `self.target.run`, no `subprocess`, nothing that touches a device or the network.
- `tests/` — pytest over `record.py`, constructed inputs, every branch, held to the same 100% line
  and branch coverage floor as every case's own `verdict.py`.

Every function here is certified against constructed or scrubbed board-captured inputs -- never an
invented device-output shape: the contract between what the device emits and what a function
expects is proven separately, by a case's own acceptance runs on bench.
