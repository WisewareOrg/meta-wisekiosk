# wisekiosk

The package the oeqa suite imports, under `meta-wisekiosk/lib/wisekiosk/` and reachable from bitbake
by `addpylib ${LAYERDIR}/lib wisekiosk` in [`../../conf/layer.conf`](../../conf/layer.conf). No module
in this package imports a third-party library at module scope: bitbake imports the package at parse
time, before any dependency it needs is necessarily available.

**One evaluator per folder.** Each subdirectory is one evaluator: a set of pure functions over
strings and dicts — no `self.target.run`, no `subprocess`, nothing that touches a device or the
network — with its own `tests/` directory beside it, exercised with constructed inputs for every
branch. A case in `meta-wisekiosk/lib/oeqa/runtime/cases/` collects from the device with
`self.target.run`/`copyTo` and hands the output to one of these functions; the evaluator never
collects for itself.

- `record/` — the run record: the R-line builders, the keyed hash, argv scrubbing, and the
  `/etc/buildinfo`, RAUC and boot-ordinal parsers.
- `render/` — the verdict over the two-capture render-advancing probe.
- `applied/` — the title parser and the applied verdict, plus `probe.js`, the DOM probe surf
  evaluates (no recipe; the case deploys it with `copyTo`).

Every function here is certified against constructed or scrubbed board-captured inputs -- never an
invented device-output shape: the contract between what the device emits and what a function
expects is proven separately, by the case's own acceptance runs on bench. `just test` holds this
package to a 100% coverage floor.
