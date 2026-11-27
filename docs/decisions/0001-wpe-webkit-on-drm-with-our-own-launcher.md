# 0001 — Show the page with WPE WebKit on the kernel's DRM display, from a launcher of our own

**Status:** accepted
**Decided:** 2026-11-24 (the cutover plan on #185 Evaluate WPE WebKit)
**Rev:** 2

## Revisions

- **rev 2** — 2026-11-25 — a frozen page's recovery is stated as the restart delay and the browser's start, not a fixed 10 s (#383 The page and the service come back sooner after a crash).
- **rev 1** — 2026-11-25 — first written (#185 Evaluate WPE WebKit).

## Context

The kiosk shows one page, full screen, that takes no input. The image showed it with `surf` in four
layers: an engine (WebKitGTK), a toolkit (GTK 3), a browser (`surf`) and a display server (Xorg).
Nothing on the panel needed the last three, and they could not be trimmed out: `surf` is a GTK
program and WebKitGTK is WebKit's GTK port, so removing GTK changes port and launcher together. No
stock browser is a kiosk, so the layer carried three patches to `surf`: window placement without a
window manager, reloading a page that stops answering, and retrying a load that fails.

**What the hardware fixes.**

- A Raspberry Pi Zero W: one ARMv6 core and 512 MB. Neither WebKit port has a JIT on ARMv6.
- The panel is driven through firmware KMS. Full KMS gives this panel a black picture
  ([`../display.md`](../display.md) §"Firmware KMS"), so a stack has to run on `vc4-fkms-v3d` with
  the pinned mesa.
- The engine is the dominant build cost under any option. A change to its configuration or source is
  a multi-hour rebuild ([`../image.md`](../image.md) §"What a rebuild costs"), so a stack that needs
  its engine patched pays that at every attempt and at every bump.

**What counts as evidence between the options.** A bench record: one built run of one commit on one
board through the bench runner. The records are on the bench host, outside the tree. A first
evaluation (2026-10-04 to 2026-10-06, PR #199 WPE cutover, closed) ran ad hoc builds and scripts;
its measurements cannot be tied to a build, a test and a run, so they are evidence for no option.
What it tried, and what broke, is below as design history, without its measurements.

**The criteria.** They are this record's; the sources name the needs behind them, and the numbers
name a criterion and rank nothing.

| # | Criterion | Where it comes from |
|---|---|---|
| 1 | Every requirement's check passes within its own bound on one run of the whole suite. An image passes or fails by the bounds, never against another image | The [requirements tree](../requirements/README.md): SRS001<!-- Recovers the instance to the panel -->, SRS002<!-- Motion without stutter -->, SRS004<!-- Prompt from power-on -->, SRS005<!-- Nothing on the panel but the instance -->, SRS006<!-- Memory stays bounded -->, SRS015<!-- Keyboard at the appliance as the last resort -->, SRS018<!-- Minimum resolution -->, and every other active item. The cutover plan on #185 Evaluate WPE WebKit replaced the run-time comparison the ticket asked for with this rule |
| 2 | No part of the stack is deprecated by its own upstream | #191 Replace cog with a launcher on WPE's Platform API |
| 3 | No toolkit and no display server | #185 Evaluate WPE WebKit: the page needs no GTK. The display server is this record's, for one core and 512 MB |
| 4 | The least code of ours, where it is easiest to keep: no engine patch, and no patch to another program | The rebuild cost above; `surf`'s patches |
| 5 | What the panel did with `surf` it still does, or the difference is stated | The cutover plan |
| 6 | Memory and start-up on 512 MB | #185 Evaluate WPE WebKit: the case for WPE is runtime. Display headroom and the stutter about every 40 s are goals there without bounds |
| 7 | The vulnerability scan sees the engine | #185 Evaluate WPE WebKit names the scan as part of adopting the layer |

Build time is not a criterion: the engine's compile dominates under either port. A newer engine is
not one either: the layer that carries WPE WebKit 2.54.3 carries WebKitGTK 2.54.3.

## Decision

**WPE WebKit shows the page through its own platform API's DRM backend, started by `kiosk-browser`,
a launcher of ours that is one C file.** The image has no X server, no compositor, no GTK, no libwpe
and no other browser. The engine comes from the `meta-webkit` layer, pinned by commit.

- **The launcher owns what `surf`'s patches owned, and the panel's console.** It retries a failed
  load in place, tells systemd's watchdog the page is alive each time the page answers a question,
  and exits when another console is brought forward, which is how that console gets the panel.
- **The engine repaints whole frames.** Its paint-damage propagation, on by default, is switched off;
  a build without that switch stops the browser rather than running with it on.

## Alternatives considered

The plan took the choice and named the launcher; this study was written after it, from the sources.
It weighed four stacks, the variants tried inside them, and an engine patch. Only the first and the
last stack have records.

**What was measured, and why.** The target suite through the bench pipeline, because it is criterion
1 and the only instrument whose result can be tied to a build: the pipeline builds the commit,
installs it over the air on the bench board and runs the suite, and the board reports the commit it
is running. A pass says each check is within its item's bound, and nothing of better or worse.

| Check | Why it was read | What it cannot show |
|---|---|---|
| TST012<!-- Cold boot to the panel --> | Start-up, the part of the runtime case a person notices | Ends when the browser reports the page loaded, not when the app has applied its configuration |
| TST014<!-- Memory over a long run --> | Whether memory grows or fills the board | One process against another; what the GPU holds; anything slower than its period |
| TST009<!-- Motion stutter measured --> | The stutter a person sees, counted by the page between its own animation callbacks | The glass, and drawing off the page's main thread; frame rate; the spacing of the stutter |
| TST001<!-- Browser killed -->, TST005<!-- Frozen page recovered -->, TST011<!-- Restart to the panel -->, TST032<!-- Backend crash -->, TST033<!-- Backend late at boot -->, TST034<!-- Browser start during a backend crash --> | What the launcher must bring back | Faults these do not induce |
| TST007<!-- Display blanking disabled -->, TST013<!-- No pointer on the panel -->, TST027<!-- Shell from an attached keyboard -->, TST030<!-- Instance covers the whole panel -->, TST031<!-- Display at the minimum resolution --> | The display path | The glass past the buffer the display driver reports |

The two performance bounds were set on the `surf` image before this decision: the motion bound is
one and a half times the worst of 20 `surf` windows, the memory growth bound about twice one clean
window (#257 Performance baseline). The plan left every bound as it was. The stacks are read by
different instruments: the page through an X window title on one, and through its inspector and the
launcher's status on the other, the motion and memory checks included, and the panel through X on
one and the kernel's display state on the other. Their figures therefore cannot be set against each
other, and each is stated alone.

**The records.** The rule for both stacks: every record of the whole suite that the runner closed as
passed, at any commit, and no selection of the suite. All are of the bench board and 33 of 33
passed. Memory is the peak share in use and the growth over the run, and every figure is within its
bound. The launcher as decided has no record under this rule.

**Stay on `surf`, WebKitGTK and X.** It passes, the scan knows its engine, and it needs no new pin.
`surf` is another project's browser, so each of its three patches must follow a bump of it, and the
two that recover a page live in its main loop. `meta-webkit` carries a newer WebKitGTK; whether
`surf` builds against that was not tried.

- `20261122T065401Z`, commit `9ae57f0` (not on main): power on to page 54.7 s; memory 45.5 %,
  50.1 MB; 5 long frames.
- `20261123T105055Z`, commit `8b5f4af`: power on to page 53.8 s; memory 45.7 %, 45.7 MB; 11 long
  frames.
- `20261123T235152Z`, commit `6d7ecfe`: power on to page 56.8 s; memory 44.8 %, 53.8 MB; 14 long
  frames.
- `20261124T020638Z`, commit `4e41102`: power on to page 68.7 s; memory 45.5 %, 47.4 MB; 19 long
  frames.

Rejected on criteria 3 and 4. What staying offers and the decision gives up: the behaviour under
Consequences, scan coverage of the engine, and the checks that read the panel from X.

**WPE WebKit under cog, the stock launcher.** Named first by #185 Evaluate WPE WebKit: a stock
launcher that drives DRM directly, so less code of ours on paper. It runs WPE on libwpe, through
WPEBackend-fdo. WPE's post on the 2.54 series says the libwpe-based API is *"officially deprecated:
it remains available and maintained, but new code should target WPEPlatform"*, and that *"this also
applies to Cog, which will not have stable releases beyond the 0.18.x series"*
([wpewebkit.org, 2.54](https://wpewebkit.org/blog/2026-09-16-wpewebkit-2.54.html)). No record of it
exists, and nothing here rests on a figure of it. The first evaluation ran 2.44.4 and 2.54.0 and
found:

- **2.44.4** drew the page at 1280x720 straight to DRM. Accelerated compositing, which the `surf`
  image ran with off, cannot be switched off in it.
- **2.54.0** alternated regions of the panel between old and new content. Switching off either of
  two paint-damage features stopped it; 2.44.4 did not show it. By source, the libwpe path draws
  every frame into one target whose buffers rotate behind it, which matches and is not proof. Whether
  the platform API path does it is not known, which is why the decision switches the feature off.
- **Compositing off on 2.54.0** crash-looped the web process on a second frame request in
  WPEBackend-fdo. A fix was read as three engine changes, 50 to 80 lines in all, at one rebuild for
  each attempt, and not built. **CPU rendering** showed a black panel.
- **Two patches were carried to cog.** One ran a script and printed the page's title for the
  evaluation's harness, and is not inherent. The other, making a display that cannot be opened fatal,
  is. How cog handles a page that stops answering, or a load that fails, was not read.
- **It crashed each time the service stopped**, for a cause not isolated.

Rejected on criterion 2, with the inherent patch against it on criterion 4.

**A minimal Wayland compositor between WPE and the display.** Named by #185 Evaluate WPE WebKit as a
candidate. Weston 13.0.1 and seatd are in the pinned poky, cage in no pinned layer, and WPE would be
rebuilt with its Wayland backend. It adds a process whose memory nobody has measured on
this board, an engine rebuild and seatd, and offers in return the hand-over of the panel to another
console, which the launcher does in about 22 lines. Never built or measured. Rejected on criterion 3.

**WPE WebKit on its platform API, with a launcher of ours.** Chosen. The first evaluation's launcher
(220 lines) reproduced cog's switches and set the display mode itself; it has no record. The launcher
decided is 134 lines, at this decision, with no switches, and leaves the display mode to the kernel.
It is built for ARMv6 against the pinned mesa and runs on firmware KMS.

- `20261124T092312Z`, commit `3e2a3f5`: power on to page 43.3 s; memory 29.3 %, 1.2 MB; 14 long
  frames. The first image of this decision: its launcher restarts the browser on a failed load, shows
  no console and leaves damage propagation on.

The whole suite on the launcher as decided failed four checks, because the build host had no space
for their test update; selections of the suite on the same launcher source passed. The merge queue
runs the whole suite on the commit that lands this record.

**Compositing off, on the chosen stack.** On the platform API this is a runtime setting, not a patch:
WPE 2.54.3 selects a non-composited renderer when the feature is off, and its release notes offer it
for embedded devices with weak GPUs. Whether the panel draws it was not tried. Not chosen, because
nothing measured on this stack asks for it.

**Patching the engine**, for the libwpe path or for console handling in the DRM backend: small in
lines, carried at every bump, and one rebuild for each attempt. Rejected on criterion 4; the damage
switch is a public setting.

**Not candidates.** The engine's MiniBrowser and its Qt binding are excluded by the recipe, which
makes each depend on `wpebackend-fdo`. Engines other than WebKit are outside this study.

**What #185 Evaluate WPE WebKit asked.**

1. *Does the layer support the pinned poky, and WPE ARMv6 and this GPU stack?* Yes: the record above.
2. *What depends on X11?* The suite's page and panel reads, the `import` screenshot and the soak
   sampler's browser name. Each is replaced; what that cost is under Consequences.
3. *Runtime against the `surf` image?* Not answered. The records hold start-up and memory of each
   image alone; per-process memory, first paint and a soak past 30 minutes were not measured, and
   the plan replaced the comparison with the bounds.
4. *What breaks in the tooling?* The skills and tools that named `surf` or X, changed or removed with
   it. The engine's remote inspector is kept.

**Against the criteria.** *Met* is a reading of the sources or the records, never a comparison of
figures.

| # | `surf`, GTK, X | WPE, cog | WPE, compositor | WPE, our launcher |
|---|---|---|---|---|
| 1 | Met | No record | No record | Met by the first image's record; the merged commit by the queue |
| 2 | Not read; nothing rests on it | Not met: libwpe and cog | Met: the platform API's Wayland backend | Met |
| 3 | Not met: both | Met | Not met: a compositor | Met |
| 4 | Not met: three patches | Not met: one inherent patch | Met: no patch, two recipes more | Met: no patch, one launcher file; plus a screen reader and a screenshot tool |
| 5 | Kept by definition | Not checked; crashed at each stop | Not checked; would carry the console switch | Differences are under Consequences |
| 6 | Within the bounds | Not measured | Not measured | Within the bounds |
| 7 | Met: the recipe names its product | Not met: it names none | Not met: the same recipe | Not met: the same recipe |

**What decides it.** Structure, not a figure: the chosen stack is the only one that meets criteria
2, 3 and 4, and criterion 7 is the one it loses to staying. Criterion 6 decides nothing, and no record
shows that headroom or the stutter is better. Staying fails no check; its cost is a toolkit, a display
server and patches to another project's browser, for a page that needs none of them.

## Consequences

- **One C file replaces a browser, its patches, an X server and a toolkit.** It is ours alone to
  keep, has no second user, and is written against an interface WPE calls stable from 2.54.
- **The cost of losing X is ours too.** `import` goes, so the image gains `kiosk-drmgrab`, a screen
  reader of 87 lines of C, and the tree gains `kiosk-screenshot.py`, 158 lines, that drives it, both
  counts at this decision.
- **The page is composited on the GPU.** The `surf` image ran with accelerated compositing off, for
  reasons recorded on #100 GPU-accelerated compositing; none of them was read on this stack.
- **Behaviour that changes from the `surf` image:**
  - Restarting the kiosk's service does not bring the page's console forward; `chvt 1` does.
  - A frozen page's recovery shows the console for the restart delay and the browser's start.
  - The frozen-page watch covers start-up, and a page that answers with a script error is not alive.
    No test covers a page that hangs while loading.
  - Cookies and local storage do not survive a browser restart. The pinned application uses neither,
    checked at its pinned commit.
  - The journal has no page-loaded event, and the boot profile no complete-display time.
  - The renderer settings and the `KIOSK_INSPECTOR` switch in the site's `kiosk.conf` are ignored.
  - A screenshot can delay a console switch by a few seconds.
  - Ctrl-Alt-Del reaches the kernel, by source and not by test.
  - tty1 has no login prompt; the keyboard's console is tty2.
- **Given up:** sites whose `KIOSK_URL` page uses audio, video or WebGL, which the engine is built
  without. The checks that read the panel from X; the suite runs on one stack and not the other, so
  the two cannot be measured side by side.
- **The vulnerability scan does not see the engine.** The pinned `wpewebkit` recipe sets no
  `CVE_PRODUCT`, so the scan looks for it under the recipe's name, and the build's NVD
  snapshot files WPE's CVEs under `wpe_webkit`. No CVEs for it is then not a finding of none, as
  [`../cve-and-sbom.md`](../cve-and-sbom.md) §"What `coverage` bounds" says of any such recipe.
- **The motion and memory bounds were set on `surf` and stand as they are**, per the cutover plan.
- **One more pin to track.** `meta-webkit` joins the pins, and its bump rebuilds the engine, as
  poky's does ([`../image.md`](../image.md) §"What a rebuild costs").
- **Not proven.** By test: a display that cannot be opened stopping the browser with its reason, a
  load retried in place and not by a restart, a first failure logged, the page returning with its
  console, and a clean exit when stopped. By comparison: that a region stays stale with damage
  propagation on, or that a stale region would be seen with it off. Also a pointer drawn into the
  page's own picture, a panel that powers itself down, the glass past the buffer, the weeks a panel
  runs, and the wall-mounted board, of which no record exists.

**Premise that would reopen this:** a requirement that misses its bound on a run of the suite and
cannot be met on this stack; the panel seen stale with damage propagation off; composited rendering
shown to be the stutter's or the board's limit, with non-composited rendering untried; the DRM
backend deprecated, or the layer dropping the pinned poky release; a page that needs audio, video or
WebGL; or a second surface beside the page, which makes the compositor the option already analysed.
A faster figure from another stack is not that premise: the rule compares with nothing.
