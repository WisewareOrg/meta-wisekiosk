# meta-wisekiosk/lib/oeqa/runtime/framework

The shared base every device test in [`../cases/`](../cases/README.md) builds on — a library, not a
test, so it is not discovered as one. Made importable as bare `framework` by `layer.conf`'s
`addpylib ${LAYERDIR}/lib/oeqa/runtime framework`;
[`docs/testing.md`](../../../../../docs/testing.md) §"The hand-run path" has the mechanism and the
two import conventions it requires.

- `base.py` — `WiseKioskCase`, the once-per-run record (role and hostname refusal, the boot/image/
  app/sut lines) every case inherits, plus the device plumbing every probe-reading case shares:
  `arm_probe()` (deploy `probe.js`, restart `kiosk.service`), `titles()` (the one window-title
  walk), `wait_applied(seconds)`. Imports `oeqa`, like a `case.py`, so it is outside `just test`'s
  coverage population the same way.
- `probe.py` — the window-title channel's own primitives: `MARKER`, `WM_NAME`, `title_lines`
  (xprop's raw dump to one title per window) and `fields` (a title's `key=value` tokens as a dict).
  Every case's own `verdict.py` parses from these rather than redefining its own marker and regex.
- `record.py` — the run record's own parsers, scrubbers and R-line builders. Pure: no
  `self.target.run`, no `subprocess`, nothing that touches a device or the network.
- `tests/` — pytest over `probe.py` and `record.py`, constructed inputs, every branch, held to the
  same 100% line and branch coverage floor as every case's own `verdict.py`.

Every function here is certified against constructed or scrubbed board-captured inputs -- never an
invented device-output shape: the contract between what the device emits and what a function
expects is proven separately, by a case's own acceptance runs on bench.
