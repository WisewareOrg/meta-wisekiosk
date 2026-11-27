# The loop, and what to check before trusting a number

The operational form of [`SKILL.md`](SKILL.md), which holds the reasoning behind each step.

## The loop

1. **State the hypothesis and the metric that can falsify it**, and decide which number ends the
   question — before any capture. A metric chosen after the data is a metric fitted to it.
2. **Write the probe and its parser off the board.** Probe: minimal per-frame work, identical in
   every arm, arms interleaved `W,A,B,A,B,A`, an in-band landing check on the computed value.
3. **Prove the parser both ways** on constructed payloads — landed and not landed — before it sees
   a board number.
4. **Write the measurement as a diagnostic test** under `tests/diagnostics`. It turns the inspector
   on with `board.app.turn_the_inspector_on`, runs script in the page with
   `board.app.inspector.evaluate`, and records what it measured.
5. **Run it through the bench driver** — `bench test <ref> --skip-build -- tests/diagnostics -k
   <name> -rP` against the board as it is, or without `--skip-build` to build and install `<ref>`
   first ([`docs/testing.md`](../../../docs/testing.md) §"Running it").
6. **Inside the test, confirm the intended page loaded** before trusting anything the capture
   produces.
7. **Capture** long enough that the warm-up block is a discard rather than a fraction of an arm.
8. **Assert the payload is non-empty.** An empty read fails the run; it never scores as a null.
9. **Parse.** Drop every block whose landing check failed; an arm with no landed blocks is
   unmeasured, not unchanged.
10. **Let the board's cleanup run.** It turns the inspector off when the test ends; confirm the page
    renders.
11. **Keep each run's numbers apart.** The bench record names board and commit; one board, one
    build and one test per table.

## Before you trust a number

- [ ] Interleaved A/B/A — not a before/after pair?
- [ ] Landing check in band, on the **computed** value, inside the same window as the number?
- [ ] Parser proven to report both outcomes on constructed payloads?
- [ ] Payload asserted non-empty, with an empty read failing loudly?
- [ ] Probe not confounding — no per-element work per frame, identical work in each arm?
- [ ] Warm-up block discarded, and not taken on the first boot of a written slot?
- [ ] Intended page confirmed loaded on the board?
- [ ] Metric moves when the page moves, and tracks what a person sees?
- [ ] Measured, not derived — or labelled **DERIVED** where it is stated?
- [ ] Taken through the bench driver, so its record names the board and the commit?
