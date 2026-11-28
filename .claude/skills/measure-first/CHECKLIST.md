# The loop

The operational form of [`SKILL.md`](SKILL.md); its "What makes a number an answer" table is the
list to check a number against before trusting it.

1. **State the hypothesis and the metric that can falsify it**, and decide which number ends the
   question, before any capture. A metric chosen after the data is a metric fitted to it.
2. **Write the probe and its parser off the board.** Minimal per-frame work, identical in every arm,
   arms interleaved `W,A,B,A,B,A`, an in-band landing check on the computed value.
3. **Prove the parser both ways** on constructed payloads, landed and not landed, before it sees a
   board number.
4. **Write the measurement as a diagnostic test** under `tests/diagnostics` and run it through the
   bench driver ([`docs/testing.md`](../../../docs/testing.md) §"Running it").
5. **Inside the test, confirm the intended page loaded** before trusting the capture.
6. **Capture** long enough that the warm-up block is a discard rather than a fraction of an arm.
7. **Assert the payload is non-empty**, so an empty read fails the run and never scores as a null.
8. **Parse.** Drop every block whose landing check failed; an arm with no landed blocks is
   unmeasured, not unchanged.
9. **Let the board's cleanup run**, and confirm the page renders.
10. **Keep each run's numbers apart**: one board, one build and one test per table.
