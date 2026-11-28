---
name: measure-first
description: >-
  Look at and measure the board instead of inferring. Diagnose a running wisekiosk device that has
  no keyboard and a display whose correct state is a black screen: pick the cheapest instrument that
  can fail (a look through a `just` recipe, or a measurement as a diagnostic test under
  tests/diagnostics run through the bench driver), pick a metric that tracks what a person sees on
  the panel, A/B without the board's own drift faking the result, test a hypothesis with a cheap
  injection before paying for a build, and question the mechanism when tuning plateaus. Invoke when
  the kiosk is unreachable, blank, stale, slow to come up or suspected of leaking memory, when the
  panel stutters or judders, when a change has to be proved faster or slower on real hardware, when
  the numbers say "fine" but the fault is still seen, or when an experiment needs a probe and a
  parser.
---

# Measure first, and measure what the eye sees

The screen cannot report its own state, and the device has no keyboard, so every instrument here
replaces looking at the panel with reading something definite. The ordered loop is
[`CHECKLIST.md`](CHECKLIST.md).

## A look, or a measurement

[`docs/testing.md`](../../../docs/testing.md) §"Running it" owns the split: a **look** reads state and
changes nothing, and a **measurement** is a number something is acted on, so it is a pytest case
under `tests/diagnostics` run through the bench driver.

| Question | Instrument |
|---|---|
| Is it up, which slot is booted? | `just kiosk-status` |
| Is the panel showing the right thing, right now? | `just screenshot`; its [header](../../../tools/kiosk-screenshot.py) says how to read it and what it cannot tell |
| Is the browser fetching the page, and did its scripts run? | `just tcp-state`, on the host serving the page; its [header](../../../tools/kiosk-tcp-state.sh) says which faults it hides |
| The board does not answer and its address is unknown | `just find`; its [header](../../../tools/kiosk-find.sh) names the L2 view it used, and `none` proves only which addresses replied |
| Is memory flat or climbing over hours? | TST014 in `tests/target_suite/test_memory.py`, with `--soak` for the day-long run |
| Where is boot time going? | `just bootprofile`, through [`tests/diagnostics/test_boot_profile.py`](../../../tests/diagnostics/test_boot_profile.py) |
| Any other number | A new case under `tests/diagnostics` |

Reach for the cheapest instrument that can *fail*: a look costs seconds, a boot profile costs a boot
of the thing under diagnosis. Read the soak log before rebooting a degraded board, as a reboot
destroys the only series that could say what was happening.

## A measurement is a diagnostic test

A number taken through an ad hoc script or an ssh one-liner carries no provenance and is not
evidence; the runner's record names the board and the commit. The test reaches the board through
`tests/board/`: `board.app.turn_the_inspector_on` and `board.app.inspector.evaluate` run script in the
page, and the board's cleanup undoes every change a part makes. A diagnostic records what it measured
and judges nothing unless a bound already exists; a check against a requirement's bound belongs in
the target suite under that requirement ([`docs/testing.md`](../../../docs/testing.md) §"Writing a
target-suite test").

## What makes a number an answer

| The tell | The discipline | What skipping it costs |
|---|---|---|
| "That should be smoother — take a look" | Measure the change, then show numbers. A person watching the panel is a witness, never the instrument. | A judgement nobody can re-run, and a change that ships on an impression. |
| A conclusion reached by arithmetic on other numbers | Label it **DERIVED** or go and measure it. A derivation is a hypothesis with decimal places. | A result that rests on a figure nobody measured. |
| The mean looks fine; the fault is still seen | Wrong metric. Find the one the perception tracks — step size, simultaneity, the freeze tail. | Hours. Rare long holds hide inside a healthy mean. |
| A metric that does not move when the page moves | It is a floor of the board, not of the page. Ablate something known to be expensive; if the number holds, the metric is measuring the platform. | A board-invariant number read as a result. |
| A plain before/after pair | Interleave — `W,A,B,A,B,A`. The board drifts within a single run at flat load. | A drift-sized effect, in whichever direction the drift went. |
| A clean null | Prove the change landed, **in band**, on the computed value, inside the window that produced the number. | A manipulation the page silently dropped reads exactly like one with no effect. |
| A payload that parsed | Assert it is non-empty. An empty read fails loudly or it reads as a null. | An arm that captured nothing scores as an arm that changed nothing. |
| A parser trusted on its first real payload | Prove it reports **both** outcomes on constructed payloads first — landed and not landed. | A discriminator that cannot come out both ways discriminates nothing. |
| A probe that does per-element work every frame | Use a minimal `requestAnimationFrame` counter for frame rate, and do identical work in every arm. | The probe's own cost lands on the arm with more elements — the quantity under test. |
| The first block after a restart, or the first boot of a written slot | Discard it. Page load is not steady state, and the first boot after an update does one-off work ([`docs/updates.md`](../../../docs/updates.md) §"The first boot of a written slot"). | A warm-up window averaged into the arm it happened to start. |

Reach for the cheapest experiment that can *fail*. An injection costs minutes; a rebuild of the
image costs far more, and one that reaches WebKit costs hours
([`docs/image.md`](../../../docs/image.md) §"What a rebuild costs").

## Choosing the metric

The metric must **move when the thing under test moves** and **track what a person perceives**.
One without the other is a number that argues with the room.

- Judder is **step distance**, and step = velocity ÷ frame rate. Anything that lowers the frame rate
  enlarges the step, which is why a mean frame rate hides it.
- Simultaneity is a variable, not a constant: cost is per moving element, so a frame where two things
  move is not comparable to one where six do. Bucket by it.
- Freezes live in the tail. A mean over a bimodal distribution describes neither mode.

When the numbers say "fine" and the fault is still seen, stop tuning and change the metric.

## A cheap injection before an expensive build

Test the hypothesis by injecting script or style into the running page through the inspector,
before committing to a refactor or a build.

- A solid-fill swap answers "is the cost the content?"
- Swapping the animation mechanism (for example scrolling against transforming) answers "is the
  cost the mechanism?"
- An injection must survive the page's content security policy:
  `el.style.setProperty(prop, val, 'important')` applies; a `<style>` element or a constructed
  stylesheet is dropped without an error. Prove it landed on the computed value.

A wrong hypothesis caught by a five-minute injection is a build not spent.

## Mechanism beats tuning

When every tuning knob — velocity, easing, timing fractions — fails or backfires, the fix is
usually a different **mechanism**, not a different constant.

- **When tuning plateaus, question the mechanism.**
- **A mechanism claim is retested, not remembered.** A result taken while something else on the page
  was also changing is confounded; re-run it once the confound is gone before building on it.

## When the measurement contradicts someone

- **Your own intuition.** A reasonable change can measure worse for a second-order reason; it is
  caught only because it was measured.
- **A requested change that backfires.** Present the data plainly: no defence, no burial, no
  softening the table.
- **A requirement that cannot physically hold.** Surface the conflict with the measured cost and the
  options; never silently satisfy one side.
- **A false premise in the request.** Measure the premise before acting on it, report what it is,
  and do not guess.

## Gotchas

- **One driver of the board at a time.** Two sessions driving one board clobber each other's probes
  and restarts. Drive it from one session; write probes and parsers, and analyse, off the board.
- **`2>/dev/null` on an ssh to a board is blocked** by `.claude/hooks/guard.sh`. A suppressed probe
  cannot tell a broken check from a broken board.
- **A connection costs the board CPU.** Batch reads through
  [`tools/kiosk-ssh.sh`](../../../tools/kiosk-ssh.sh), and keep connections out of a window being measured
  ([`kiosk-bootprof`](../../../meta-wisekiosk/recipes-core/kiosk-bootprof/README.md)).
- **`pgrep -f <pattern>` matches your own command line** over ssh, so it finds your shell. Use
  `pidof` for the browser: busybox `pgrep -x` matches the full path the launcher runs as.
- **Sample twice before believing a one-shot read.** One sample cannot tell a state from a moment.
- **A failed or BLANK capture is not a frozen panel.** A panel left on a text console comes back
  with `chvt 1` ([`docs/display.md`](../../../docs/display.md)); a remote `systemctl restart kiosk`
  does not bring it forward.
- **Keep runs apart.** Numbers from different boards, builds or runs never share a table.
