# W6 recovery manifest — #100 gpu-compositing

Staged for commit beside `docs/issue_investigation/gpu_compositing/README.md` in Phase C (per the
plan's sequencing rule — not committed by this task). Layout matches that directory: files land at
its root.

Scope derived from `git show origin/100-gpu-compositing:docs/issue_investigation/gpu_compositing/README.md`
(4469 lines) against the branch's tracked file list. The README's own R2 accounting (lines ~215,
263-274) names exactly four unmet obligations; this recovery closes three of them and reports the
fourth as **not recoverable as a single file** (see "Not found" below). A full link-extraction sweep
of every `[text]` `(path)` pair in the README confirmed every *linked* file already exists on the branch —
the only gaps are items the README names in prose without a link, precisely because it says they
are not committed.

## Redaction

`tools/scrub-identity.py --check --allow-partial` (PATTERN half) ran clean against the whole staged
set (16 files, 0 hits). The KNOWN half (prod/bench/mirror addresses, SSID, PSK hash, MAC,
machine-id) was checked manually against `local/device-identity.md`'s values — 0 hits — because the
tool's KNOWN half only runs from inside a worktree that can see that gitignored file, and this
staging directory is not one.

**One redaction, in two files**: the mirror's `http://<addr>:8080/` URL in the `KIOSK_URL=` line,
present because these two captures record the exact `kiosk.conf` deployed for the run. Replaced with
`<mirror>`, matching `local/device-identity.md`'s placeholder convention. No other file in this set
contained any address, hostname, SSID, MAC, serial or machine-id — confirmed both by the pattern
scan and by a direct grep for each literal KNOWN value.

## Recovered: Runs 3-7 harness (11 files)

The README (lines 312-316) states these one-off scripts "exist only in a scratch directory outside
this repository" and were never committed. They were not found on this host's live filesystem (a
prior recon's `find / -xdev` found none — see `close-the-loop.md` §E1), so they are recovered from
this session's own prior transcript (`~/.claude/projects/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl`
and its subagents), which still holds the exact bytes each `Write` tool call produced.

| File | Run | Provenance | sha256 |
|---|---|---|---|
| `probe.sh` | 3 | subagent `a773faf4212624f5d`, transcript line 99 (`Write`, verbatim) | `2b82b500b90a7582815c445a6053fb3f6a86c51c1b141de4d0433dfe12ef06fd` |
| `inspect3.mjs` | 5 | subagent `a88a245c9038e113f`, line 92 (`Write`, verbatim) | `dad27c0531cc49cad649c3e91ad73c9092e43e57da5f0253fd02af57d59748b7` |
| `exp2-script.js` | 6 | subagent `a45d0bf2462047d92`, line 162 (`Write`, verbatim; deployed unmodified at lines 166/169) | `ccf07b7df8a0217113b29b06473ffbe538955c1cd9d1d57d5d0e144762202a18` |
| `exp3-script.js` | 6 | subagent `a45d0bf2462047d92`, line 171 (`Write`, verbatim; deployed unmodified at line 178) | `94835e6f55c26c5253f9740b5add6024c566728a8b711ddf0afb00d1391106d0` |
| `exp4-script.js` | 6 | subagent `a45d0bf2462047d92`, line 182 `Write` base, then the in-place `build()`/`cs()` patch applied at line 187 before deployment at line 190. **This staged file is the post-patch (deployed) form, not the line-182 base** | `5d87bf49dc89d90357c3674e4110164ee5daf823010b3a0ece1550a5a737c1e2` |
| `exp5-script.js` | 6 | derived from `exp2-script.js` by the exact `str.replace()` transform in subagent `a45d0bf2462047d92` line 197 (PH/ALLSEL/ALLPROP block, `EX2`→`EX5`, `MEAS` 15000→12000), then deployed unmodified at line 199 | `c940d5d32e320e38c27505cadb3dde6ede9d3c9fd53f9326f5489b2f437fe005` |
| `exp6-script.js` | 6 | derived from `exp2-script.js` by the exact transform at line 203 (`EX2`→`EX6`), deployed unmodified at line 206 | `6ad655d048d8aafa656e189229678e3c1e50500a354ae1c09bfb62f895d7f124` |
| `diag-script.js` | 6 | subagent `a45d0bf2462047d92`, line 112 (`Write`, verbatim) | `1ce81b3c13a621fb7437bfcc9c4cd4c2a3d6548070d962e7ba1bc85ac2e21f97` |
| `diag2-script.js` | 6 | derived from `diag-script.js` by the exact `onerror`/import-probe insertion at line 122, written to `diag2-script.js` | `1507ba4250ad313f9317cec2ed53c0690b48df2bce2c47e956020e0d2934719a` |
| `exp7-script.js` | 7 | subagent `a2dc2d649d77c30fd`, line 168 (`Write`, verbatim; deployed unmodified at line 188) | `cb1130c696730a941e831ec93f52f34c11781f4f40fd2d8f746d0eddbc62350e` |
| `exp8-script.js` | 7 | derived from `exp7-script.js` by the exact transform at line 208 (`WARM/SETTLE/MEAS`, `EX7`→`EX8`, `contentSig()` simplified, `PH` block replaced with the 5-phase F1/C1 set), deployed at line 211 | `2b32ca34766dfad3408e8febe8955bb5264546f3d106f6917ed48de9c9e75cd5` |

**Version rule applied:** every derived file (`exp4`, `exp5`, `exp6`, `diag2`, `exp8`) is the
transform applied mechanically from the transcript's own Python/JS `str.replace()` call, not a
retyping — the anchor strings were asserted present (`assert old in s`) before substitution, so a
drifted anchor would have failed loudly rather than silently produced the wrong file. No ambiguity
was found: each derived file has exactly one transcript step that produced it, and it is the one
deployed to the board for that run's capture.

**No redaction needed.** None of these 11 files reference a board address, hostname or credential —
consistent with the README's own claim (line 308) that "No device address is in any of these files."

## Recovered: Run 44's named tool (1 file, not board-run, banked no numbers)

| File | Provenance | sha256 |
|---|---|---|
| `profile-churn.mjs` | main transcript `9253304a…jsonl` line 11433 (`Write`, verbatim) | `ca46f65b85ea1aefac32047a4115feeb9d2e3166bc8709bf2ce772a8ed41f5c4` |

The README (line 296) names this tool as "committed nowhere in this repository" and not the source
of any number in the record (its diff banked no numbers). Retained per the owner ruling — it was
used, even though the run it served produced no retained figures. It is superseded for future use by
the committed `webkit-inspect.mjs diff <seconds>` mode, which the README states implements the same
experiment; `profile-churn.mjs` is retained as the literal instrument Run 44 actually ran, not as a
recommended tool going forward.

## Recovered: Run 47's capture (2 files)

The README (line 213, 271) states "No capture file is committed — the arrival series is transcribed
into the run block" from "the session's own task output." That task output still exists on disk,
unaltered, at the paths below, and is reformatted here into the same raw-capture convention every
other run uses (see `baseline-588s-raw.txt` for the committed precedent):

| File | Arm | Provenance | sha256 (after redaction) | sha256 (before redaction) |
|---|---|---|---|---|
| `memory-pressure-baseline-588s-raw.txt` | 1, monitor ON (`JSC_logGC=1`) | `/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bu2x8ct82.output`, produced by main transcript line 12677 (background task, read back at lines 12682/12754) | `b3318779d7b0ab1d91313d667a19ddf6f734d735c2d50654222f82ededd01a56` | `28783b03f26a8d327f502f95f142631578d7c20cad86be9853cad10a8eb340fb` |
| `memory-pressure-monitoroff-589s-raw.txt` | 2, `+WEBKIT_DISABLE_MEMORY_PRESSURE_MONITOR=1` | same task file, `bv2ict5ht.output`, produced by line 12760 (read back at line 12791) | `e25759d6043c4a35bc42934636e346072289ca2e720c3484d1c5e6495a6bee57` | `7e126d7561d995e4bcf45fc8d3974c716c94d11acd49afc7d4917cc72484a3c8` |

**Redaction:** the `KIOSK_URL=` line in each file's `kiosk.conf` header — the mirror's
`http://<addr>:8080/` — was replaced with `<mirror>` (one line, each file).

The arrival series in both files (`S[...]` inside the `BL|` payload) is byte-identical to the numbers
quoted in the README's Run 47 block and in the corroborating scratchpad note
`memory-pressure-test-RESULT.md` (still present at
`/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/memory-pressure-test-RESULT.md`,
not copied into this staging set because it is a derived write-up, not a capture, and the plan asks
for scripts and captures).

## Recovered: soak scripts on prod `/data` (2 files, read-only copy)

Copied read-only from prod (`root@<prod>`, via `tools/kiosk-ssh.sh`, `cat` only — nothing written to
the board) on 2026-09-28. Byte counts and md5sums verified to match the on-board copies exactly
before and after transfer (`wc -c` + `md5sum` both sides).

| File | On-board path | sha256 | Note |
|---|---|---|---|
| `kiosk-soak.sh.new` | `/data/kiosk-soak.sh.new` (mtime 2026-08-15 23:01) | `25f14d143bb5122e04106aca6cbcd35512690aa6f9b93ca939bab3601da4b979` | 159 lines. Diffs from the committed `meta-wisekiosk/recipes-core/kiosk-soak/files/kiosk-soak.sh`: adds `ntpsync`/`dns`/`border`/`baleft`/`bbleft` fields (RAUC boot-counter and timesyncd instrumentation for issues #31 and #18/#26), appended at the end of the printf line so the `--summary` parser (which keys on named fields) is unaffected |
| `kiosk-soak.sh.orig-20260815` | `/data/kiosk-soak.sh.orig-20260815` (mtime 2018-03-09, i.e. image-stamped) | `ffbec4fd2d8556b62ade899c17169e8050fd44afbff2608636462799ef7a21b4` | 125 lines. Diffs from the same committed file: lacks the ts-gap detector and the reboot/gap-aware slope-suppression logic the committed version has |

Neither file was deleted from prod — the plan (Amendments, "Leftover deletion … moves to Phase C,
after W6 is committed") defers that to W9 step 6, after this recovery lands.

**No redaction needed** — neither file references a board address, hostname or credential.

## Not found as a single file: the driver actually used for Runs 26-48

`close-the-loop.md` (this session, §2 "Harness gaps a rerun hits") already established that the
*committed* `run-phase.sh` and `run-phase-motion.sh` grep only `'KP|'` / `'KP[0-9]+\|'`, while
`p7_min.js`, `p30_baseline.js` and `p31_rotcheck.js` (used for Runs 26-48) emit `MP|`/`BL|`. This
recovery traced the actual transcript mechanics for that range (main transcript lines ~8630-13700)
and confirms **no reusable driver file — named or otherwise — was ever written for this range**.
Every deploy-and-read-back for Runs 26-48 was a fresh inline `tools/kiosk-ssh.sh root@<prod> 'sh -s'
<<'EOF' … EOF` heredoc, retyped (with small variations — sleep durations, xprop id, the `MP|`/`BL|`
grep) in each Bash call. Examples: main transcript line 8630 (`grep 'MP|'`, an `xwininfo`-based
window-id scan), line 8658 (a fixed-id `xprop -id 0x600002` variant used from Run 26 onward), line
12677/12760 (Run 47's bespoke `arm1-baseline.sh`/`arm2-monitor-off.sh`, which are two of these
one-off heredocs written to scratchpad files rather than typed inline — those two are recovered
above as Run 47's capture provenance, not as a general-purpose driver).

There is therefore nothing byte-identical to retain under the "every used script is retained" ruling
for this item — the mechanism was never a script, only a repeated typed pattern. **Escalating, not
inventing:** whether to synthesize a new committed driver from this pattern (which is what the
plan's W10 fallback, `run-phase-appliance.sh`, already anticipates if W6 finds nothing) is a decision
for the plan owner, not a recovery. This report treats the item as **not found**, matching
`close-the-loop.md`'s independent conclusion ("The README does not name the driver used for Runs
26–48. The rerun needs a readback change committed beside the README, per R2").

## Summary (original scope, above)

- **Found and staged:** 16 files — 11 Runs 3-7 harness scripts, 1 Run 44 tool (`profile-churn.mjs`),
  2 Run 47 raw captures, 2 prod soak-script variants.
- **Not found (escalated, not invented):** 1 item — a single reusable "driver" file for Runs 26-48;
  none ever existed as such.
- **Redactions:** 1 value (the mirror address), applied in 2 files, 1 line each.

---

## Extension (owner ruling, 2026-09-28): per-run driving commands

Owner ruling: "yes, retrieve the scripts from the transcripts." For every #100 run whose driving
commands are not already committed beside the README, extract the ssh heredocs, probe deploys,
readbacks and analysis one-liners that produced its recorded number, in order, one file per run:
`runNN-commands.sh`. Source for all of them: session `9253304a-ddb2-4c2c-827e-a05b0942ac7b` (main
transcript for Runs 8-9 partially and 17-48; two subagents, `agent-abead48aed7895c20.jsonl` for Run 8
and `agent-adeb77092a2242020.jsonl` for Runs 10-16, for the probe4 family; four subagents for Runs 3,
5, 6, 7). Each file's header names its exact source lines/subagent, timestamps, and — per the
follow-up owner ruling below — a confidence level and the judgement behind it.

**Second owner ruling, same date:** "I will not know any better what ran so please just do your best
effort and judgement here" — pick the attempt whose output matches the README's recorded number,
using timestamps, output values and ordering; record the judgement (which attempt, why, the
alternatives, a confidence of high/medium/low) in each file's header and here; escalate only if
nothing in the transcripts ties to a run at all. This superseded the first pass's decision to
escalate Runs 8-25 as a range and three smaller gaps — both are now resolved below.

### Files produced (45)

One file per run, 3 through 48 inclusive (`run3-commands.sh` covers Run 4 too — see its header;
`run26-commands.sh` covers both 26a and 26b; `run48-commands.sh` covers all three rotation arms).

### How Runs 8-25 were resolved

The first pass wrongly assumed the committed `run-phase.sh`/`run-phase-motion.sh` (or their absence)
decided which runs were "already committed." Tracing the actual subagents shows Runs 8 and 10-16 were
built and run entirely inside two dedicated subagents that never surfaced in the earlier search
(their Write/Bash calls create the probe files locally before deploying them, so a plain string
search for the probe's filename across the main transcript alone missed them):

- **Run 8** (`probe4.tmpl.js`/`p4_a.js`/`p4_b.js`/`p4_d.js` → `phaseA.txt`/`phaseB.txt`/`phaseD.txt`/
  `phaseA2.txt`): subagent `agent-abead48aed7895c20.jsonl`. One clean pass per file, `./run-phase.sh
  <probe> <secs> > <file>`, immediately parsed with a label matching the README's own per-arm text.
  No retries.
- **Runs 10-16** (`p5_clock.js`, `p6_title.js`, `xcpu-sample.sh` (two arms), `p7_min.js`,
  `p8_layers.js`, `p9_area.js`, `p10_noanim.js`): subagent `agent-adeb77092a2242020.jsonl` (1385
  lines). Each run is one clean `cat > script.js < <probe>` deploy followed by one `kiosk-ssh.sh ...
  'sh -s' > <raw-file>` capture — a repeating, unambiguous pattern with no retries anywhere in this
  range. A great many identical one-line polling calls (`echo "lines=$(wc -l ...)"`, waiting for the
  background ssh to finish) sit between deploy and analysis in the source subagent; they are
  collapsed out of the command files as pure polling noise, not as an exclusion of anything that
  drove the run.
- **Run 9** (`p4_a.js` again, after the park-card remount fix, → `hang-after-raw.txt`): main
  transcript. The first attempt (line 6478) was **rejected outright** (the tool use was declined) and
  never ran; the identical retry (line 6623) succeeded. Picked on that basis, and independently
  confirmed: the retry's capture carries `ROT0` and a `250`ms-and-over rate of 308/287s = 1.073/s,
  matching the README's cited "ROT 97 → 0" and "1.07/s" exactly.
- **Run 17** (`p12_motion.js` → `motion-baseline-raw.txt`): the deploy at line 7212 used the
  not-yet-parameterised `run-phase.sh`, whose *own* readback (`grep 'KP|'`) cannot match this probe's
  `KP2|` payload — so that command's own capture (`during-motion-raw.txt`) is empty and uncatalogued.
  But the `cat > script.js` half of that same command did land the probe, which kept accumulating
  state on the board for roughly 27 minutes until a standalone `xprop` poll at line 7417 read it back
  successfully — and that payload is byte-for-byte the one committed as `motion-baseline-raw.txt`.
  Picked on that exact string match between the tool result and the committed file, not by proximity.
- **Runs 18-23, 25**: each a single clean `run-phase-motion.sh <probe> <secs> > <file>` pass with no
  retries, all using the now-parameterised, committed-form driver.
- **Run 24** (`p12_motion.js` → `motion-linear-shrunk-raw.txt`): the first attempt (line 8434) was
  **blocked by `guard.sh` itself** (a `2>/dev/null` on an ssh probe, caught by the project's own hook)
  and never ran; the retry without that redirection (line 8446) succeeded. Not a close call — the
  blocked attempt could not have produced anything.

All of Runs 8-25 are HIGH confidence except Run 12 and 15, MEDIUM — see each file's own header for
the specific reasoning; none required a judgement call between two attempts that both ran and might
each explain the recorded number (the only genuine competitions found were reject-then-retry pairs,
resolved because the first half of each pair never executed at all).

**Run 3/4 boundary — not picked, and said so.** Run 4 runs "by continuity" inside the same unbroken
ssh session as Run 3 (no redeploy, no restart, no config write — the README's own basis statement).
No command marks where Run 3's reading ends and Run 4's begins, so `run3-commands.sh` carries the
full ordered sequence for both rather than an invented split point — this is a structural continuity,
not a contest between competing attempts, so it does not fall under the "pick the matching attempt"
ruling; there is nothing to pick between.

**Included with a caveat, not excluded — Run 3's remote-inspector sub-thread.** Within
`run3-commands.sh`, main-subagent lines ~224-297 (2026-09-21T19:29:15Z-19:34:56Z: `wsinspect.py`,
`inspect_eval.py`, `expr1.py`/`expr2.py`/`discover*.py`/`dbg.py`/`start_*.py`, an SSH port-forward to
the WebKit inspector) is a **failed** attempt to read frame timing over the remote inspector — it
produced no number cited in Run 3's block. It sits *between* two commands that plainly do belong to
Run 3 (the causal-arm script prep `pause.js`/`blank.js` immediately follow it and could not be cleanly
lifted out without risk of losing something load-bearing), so it is left in rather than surgically
cut.

### Three smaller gaps, now resolved

- **Run 40's deploy line** (previously reported missing): it was there all along, embedded at the end
  of main transcript line 10771, which opens with a bundle-marker check and closes with `cat >
  /home/root/.surf/script.js < .../p29_split.js` — my first pass under-read that command's full text.
- **Run 45's config-set command** (previously reported missing): main transcript line 11766, which
  sets `JSC_percentCPUPerMBForFullTimer` to the default divided by 16 (matching the README's "16x
  less eager full-collection timer") and deploys `p30_baseline.js` in the same command.
- **Run 48's 8s-arm config provenance** (previously reported missing): still not fully traced — no
  explicit restore of `config.json` back to the schema default was found between the 6s arm (line
  13397) and the 8s-arm deploy (line 13437); the first check confirming the file was "clean" happens
  only afterward, at line 13495. This is **not** escalated, because it does not put which command
  drove the 8s arm in question — line 13437 is a single, unambiguous deploy+capture, and its own
  capture carries an `R[]` median of 8.000s, matching the README's cited value. What is untraced is
  only how the environment reached that state, not which command produced the number. Noted in
  `run48-commands.sh`'s header as the one point this recovery could not fully close.

### Excluded as unrelated exploration (by timestamp, main transcript unless noted)

- 2026-09-22T18:57:34Z-18:58:06Z (lines 8608-8630): reading `deployed-scroll-raw.txt`, an
  **uncatalogued** capture from an earlier session — the README attributes it to no run.
- 2026-09-22T19:58:08Z-20:12:24Z (lines 8911-9059): a remote-inspector reachability probe
  (`wsinspect`/websocket tunnel) between Runs 28 and 29; produced nothing cited.
- 2026-09-22T20:18:23Z-20:21:44Z (lines 9059-9075): a `hide.js` scratch experiment plus a WebKit
  string search, between Runs 29 and 30.
- 2026-09-22T22:09:33Z-22:11:45Z (lines 9346-9367): a WebKit string search for compositing/tiling env
  vars — research that informed Run 33's config choice but is not itself a driving command.
- 2026-09-22T22:11:45Z (line 9372): a screenshot capture, evidentiary but outside the MP|/BL|
  readback chain.
- 2026-09-22T22:39:02Z-23:53:39Z (lines 9490-9566): board display-state documentation plus an
  identity-leak fix applied to two **deliverable** files — unrelated to any run's capture.
- 2026-09-23T00:00:11Z-01:05:46Z (lines 9649-9730): JSC GC env-option research and orphaned
  background-task housekeeping, preparatory to Runs 37-48 but not a driving command.
- 2026-09-23T01:26:12Z-01:39:37Z (lines 9834-9930): a woff2-recipe check, root-README cleanup, and a
  `git commit`/`git push` of the Test-runs table edits.
- 2026-09-23T01:49:26Z-02:07:53Z (lines 10049-10268): board/mirror recon (docker containers, bundle
  diffing) preparatory to Run 37's instrumented bundle.
- 2026-09-23T02:21:21Z-02:25:48Z (lines 10351-10459): `parse_mqtoggle_test.py` self-test plus a
  screenshot/render-check verification and a stray-directory cleanup.
- 2026-09-23T02:33:35Z-02:47:46Z (lines 10505-10574): `JSC_logGC`/`surf-milestones.log`
  characterisation and an ssh-wrapper internals check — ancillary to Run 38, not its CAP|/GC2|
  readback (the two probe deploys and both readbacks are included).
- 2026-09-23T02:50:53Z (WiseKiosk repo) through the `docker compose up -d --build` for each: the
  frontend edits and rebuilds that produced instrumented bundles `index-CDzciXkW.js` (Run 37),
  `index-CqqUlNUO.js` (Run 39) and `index-BM3R3o7e.js` (Run 40). **Escalated, not excluded on a
  judgement call**: these are a different repository's source edit and build step, not an ssh
  heredoc/probe-deploy/readback against the kiosk, so they sit outside this ruling's named categories
  — but they did produce the bundle each run measured. Whether to recover them too is for the plan
  owner.
- 2026-09-23T03:07:48Z (line 10750): a `svelte-check` lint run in WiseKiosk, unrelated.
- 2026-09-23T04:51:47Z-05:00:04Z (lines 11309-11400): earlier failed `inspect-timeline.mjs` attempts
  and a `git commit`+`git push` of README edits, before the working `gc 85` / `profile-churn.mjs 30`
  invocations used for Run 44.
- 2026-09-23T05:15:00Z-05:16:49Z (lines 11470-11493): board-state recon before Run 43's clean-config
  deploy.
- 2026-09-23T12:52:46Z-12:59:30Z (lines 13176-13283, WiseKiosk repo): `config.json`/compose
  investigation and container-restart debugging preceding Run 48's 12s arm.
- 2026-09-23T13:02:52Z (line 13330): an unrelated README-wording grep, interleaved between two of
  Run 48's arms.

### Redaction (second pass, across all 45 command files)

Unlike the scripts/captures above, these command files are literal `ssh`/`kiosk-ssh.sh` invocations
and so are dense with the board addresses. Applied globally, longest-match-first:
prod address → `<prod>`, mirror address → `<mirror>`, bench address → `<bench>` (present in none),
router address → `<router>` (present in none), bench hostname → `<bench-hostname>`, wifi SSID →
`<wifi-ssid>`, wifi PSK hash → `<wifi-psk-hash>` (present in none), board MAC → `<board-mac>`
(present in none), machine-id → `<machine-id>` (present in none).

**Counts per file** (placeholder → occurrences; no literal value below):

| File | Redactions |
|---|---|
| run3-commands.sh | `<prod>`×53, `<bench-hostname>`×1, `<wifi-ssid>`×1 |
| run5-commands.sh | `<prod>`×16, `<bench-hostname>`×1, `<wifi-ssid>`×1 |
| run6-commands.sh | `<prod>`×43, `<mirror>`×20 |
| run7-commands.sh | `<bench-hostname>`×1 (prod is resolved at run time via `local/device-identity.md`, never hardcoded, in this file's commands) |
| run26-commands.sh | `<prod>`×9 |
| run27-commands.sh | `<prod>`×4 |
| run28-commands.sh | `<prod>`×2 |
| run29-commands.sh | `<prod>`×4 |
| run30-commands.sh | `<prod>`×4 |
| run31-commands.sh | `<prod>`×4 |
| run32-commands.sh | `<prod>`×2 |
| run33-commands.sh | `<prod>`×5, `<mirror>`×1 |
| run34-commands.sh | `<prod>`×5, `<mirror>`×1 |
| run35-commands.sh | `<prod>`×4 |
| run36-commands.sh | `<prod>`×4 |
| run37-commands.sh | `<prod>`×4 |
| run38-commands.sh | `<prod>`×8 |
| run39-commands.sh | `<prod>`×3, `<mirror>`×2 |
| run40-commands.sh | `<prod>`×3, `<mirror>`×2 |
| run41-commands.sh | `<prod>`×3 |
| run42-commands.sh | `<prod>`×2 |
| run43-commands.sh | `<prod>`×3 |
| run44-commands.sh | none (no address in either command) |
| run45-commands.sh | `<prod>`×1 |
| run46-commands.sh | `<prod>`×2 |
| run47-commands.sh | `<prod>`×5 |
| run48-commands.sh | `<prod>`×3, `<mirror>`×3 |
| run8-commands.sh | `<prod>`×1 |
| run9-commands.sh | none (the scratchpad `run-phase.sh` bakes the address inside the script file, not on the command line that invokes it) |
| run10-commands.sh | `<prod>`×5 |
| run11-commands.sh | `<prod>`×3 |
| run12-commands.sh | `<prod>`×4 |
| run13-commands.sh | `<prod>`×3 |
| run14-commands.sh | `<prod>`×3 |
| run15-commands.sh | `<prod>`×3 |
| run16-commands.sh | `<prod>`×3 |
| run17-commands.sh | `<prod>`×2 |
| run18-commands.sh | `<prod>`×2 |
| run19-commands.sh | `<prod>`×5, `<mirror>`×1 |
| run20-commands.sh | `<prod>`×1 |
| run21-commands.sh | `<prod>`×1 |
| run22-commands.sh | `<prod>`×3 |
| run23-commands.sh | `<prod>`×1 |
| run24-commands.sh | `<prod>`×4 |
| run25-commands.sh | `<prod>`×1 |

A side effect worth naming: three of `run3`/`run5`/`run7`'s commands are themselves in-session
**leak-check greps** for the literal hostname/SSID string, run against a deliverable to confirm it
was clean. Redacting those turns the check into a search for the placeholder text instead of the
real value — a harmless side effect of redaction, not a new defect, left as-is rather than
special-cased.

**Verification:** `tools/scrub-identity.py --check --allow-partial` (PATTERN half) ran clean across
all 62 staged files (0 hits) at every pass. A manual grep for each literal KNOWN value (the prod,
bench and mirror addresses; the wifi SSID and hostname named in `local/device-identity.md`; the PSK
hash; the machine-id; the MAC — none reproduced here, see that file for the values) across the full
`w6-recovered/` directory returns zero matches, confirmed after every edit made to any file in this
set, including the two fix-ups this second pass found: an unredacted address in `run45-commands.sh`
left over from inserting its resolved config-set command after the first redaction pass ran, and this
manifest's own earlier draft of this paragraph, which had quoted several of the literal values it was
describing — both fixed in place.

### Extension summary

- **Extracted:** 45 `runNN-commands.sh` files covering Runs 3 through 48 inclusive (3 covers Run 4
  too; 26 covers both 26a/26b; 48 covers all three rotation arms).
- **Confidence:** HIGH on all 45 except Run 12 and Run 15 (MEDIUM — see their headers) and Run 3
  (MEDIUM overall, for the reasons in its header).
- **Resolved on a second pass:** Runs 8-25 (originally escalated as a range) and three smaller gaps
  (Run 40's deploy line, Run 45's config-set command) — see "How Runs 8-25 were resolved" and "Three
  smaller gaps" above.
- **One item still not fully traced, not escalated:** Run 48's 8s-arm config provenance (the run
  itself ties to an unambiguous command; only the environment's path back to the schema default is
  untraced).
- **Escalated as a scope question, unchanged:** whether the WiseKiosk-repo frontend edits/rebuilds
  behind Runs 37, 39 and 40's instrumented bundles belong in this recovery too, and whether "the
  driver actually used for Runs 26-48" (no single file was ever found to exist) should be synthesized
  going forward — both are plan-owner decisions, not something to invent here.
- **Redactions:** 9 placeholder types, applied across 42 of the 45 command files (all but Run 9's and
  Run 44's, which never carry a literal address, and excepting counts of zero for placeholders not
  present in a given file).

---

## Third pass (team-lead direction, 2026-09-28): the 2-arg run-phase.sh, and the frontend patches

### `run-phase.sh.2arg-variant` — the script that actually ran for Runs 8, 9 and 17's aborted first half

Recovered verbatim from `agent-abead48aed7895c20.jsonl` line 151 (a `Write` tool call), and confirmed
byte-identical to a later `cat` of the same file at main-transcript line 6454. Staged as
`run-phase.sh.2arg-variant`, never overwriting the committed `run-phase.sh` at
`docs/issue_investigation/gpu_compositing/run-phase.sh`, which is a different script (3 positional
arguments, host on the command line) written later in the same session (main transcript line 7357)
and used from Run 17 onward. The prod address baked into the 2-arg copy (`HOST=root@<address>`) is
redacted to `<prod>`.

**Which runs used which copy, as a fact, not a fix to the README:**

| Run | Driver actually invoked | Evidence |
|---|---|---|
| 8 | `run-phase.sh.2arg-variant` (`./run-phase.sh p4_a.js 330 > phaseA.txt`, etc.) | subagent `agent-abead48aed7895c20.jsonl`, lines 153/171/189 |
| 9 | `run-phase.sh.2arg-variant` (`./run-phase.sh p4_a.js 300 \| tee hang-after-raw.txt`) | main transcript line 6623 (line 6478's identical attempt was rejected and never ran) |
| 17 (aborted first half) | `run-phase.sh.2arg-variant` (`./run-phase.sh p12_motion.js 240 > during-motion-raw.txt`) | main transcript line 7212. Its own readback (`grep 'KP\|'`) cannot match this probe's `KP2\|` payload, so `during-motion-raw.txt` is empty/uncatalogued — but the `cat > script.js` half of the same command did deploy the probe, which is what a *later*, unrelated command (line 7417) eventually read out as Run 17's real capture (see the Extension's "How Runs 8-25 were resolved") |
| 10, 11, 12, 13, 14, 15, 16 | **Neither driver.** Ad hoc `tools/kiosk-ssh.sh ... 'sh -s'` heredocs, hand-written per run, no wrapper script at all | subagent `agent-adeb77092a2242020.jsonl` (see its per-run lines in each `runNN-commands.sh`) |
| 18-25 | The **3-arg, currently-committed** `run-phase.sh` / `run-phase-motion.sh` | main transcript, `./run-phase-motion.sh root@<prod> <probe> <secs>` invocations from line 7537 onward |
| 26-48 | Neither driver; ad hoc heredocs (already reported — see "Not found as a single file" above) | main transcript |

**The discrepancy, stated as a fact:** the README's own harness section says "The `probe4` family — the
harness Runs 8 to 13 share... `run-phase.sh` is the driver and takes the board role's address on its
command line." That is true only for Run 8 and (by reuse) Run 9. Runs 10 through 13 (`p5_clock.js`,
`p6_title.js`, `xcpu-sample.sh`, `p7_min.js`) never invoke any `run-phase.sh` — each is a bespoke
inline heredoc built by hand in a different subagent. This recovery reports that fact; it does not
edit the README to correct it.

**Runs 8-13, cited capture vs. produced capture:**

| Run | README's Runs 8-16 catalogue cites | Transcript shows this file was actually produced | Match? |
|---|---|---|---|
| 8 | `phaseA.txt`, `phaseA2.txt`, `phaseB.txt`, `phaseD.txt` | same four, via `run-phase.sh.2arg-variant` | Yes |
| 9 | `hang-after-raw.txt` | same, via `run-phase.sh.2arg-variant` (the retry, not the rejected first attempt) | Yes |
| 10 | `clock-ablation-raw.txt` | same, via an ad hoc heredoc (not `run-phase.sh`) | Filename yes, mechanism no |
| 11 | `title-cadence-raw.txt` | same, via an ad hoc heredoc | Filename yes, mechanism no |
| 12 | `xcpu-noprobe.log`, `xcpu-probe.log` | same two, via an ad hoc heredoc plus the separately-committed `xcpu-sample.sh` | Filename yes, mechanism no |
| 13 | `minprobe-raw.txt` | same, via an ad hoc heredoc | Filename yes, mechanism no |

Every cited filename was in fact produced; what the README overstates is *how* — a single shared
driver script — for four of the six runs in this range.

### `runNN-frontend.patch` — the WiseKiosk-repo edits behind Runs 37, 39 and 40's instrumented bundles

Recovered from the `Edit` tool_use inputs in the main transcript (the file each targets,
`frontend/src/modules/.../*.ts`/`*.svelte`, was **untracked** in WiseKiosk at the time — confirmed via
`git status` at main-transcript line 10060 for Run 37's file — so there is no git blob to diff
against; these commands are the only record of the change). Checked against WiseKiosk's git history
(`git log --all -- <path>` and a search for "mqAlloc"/"Run 37"/"Run 39"/"Run 40") and confirmed **not
committed anywhere** in that repository — each carries its own "strip before ship" comment, and none
ever shipped. Format: a hand-built unified diff, one hunk per `Edit` call in transcript order, headed
`@@ hunk N of M -- transcript line L, <timestamp> @@` instead of a real `@@ -a,b +c,d @@` line range,
because no base file revision exists to compute real line numbers against — this is a faithful
before/after record of each edit, not a `git apply`-ready patch.

- **`run37-frontend.patch`** — `frontend/src/modules/park_wait_times/marquee-clock.ts`, 4 hunks
  (transcript lines 10159, 10170, 10174, 10183). The ALLOC/CLEAN toggle README's Run 37 block
  describes: a `window.__mqAlloc` switch between the Map-iterator path and a flat-array path,
  landing-checked by per-path frame counters.
- **`run39-frontend.patch`** — two files in one patch: `frontend/src/modules/park_wait_times/ParkWaitTimes.svelte`
  (1 hunk, transcript line 10618 — line 10601's identical edit failed with `File has not been read
  yet` and never applied) and `frontend/src/modules/clock/Clock.svelte` (1 hunk, transcript line
  10621). The rotation-tick and clock-read ablation switches README's Run 39 block describes.
- **`run40-frontend.patch`** — `frontend/src/modules/park_wait_times/ParkCard.svelte`, 2 hunks
  (transcript lines 10723, 10726). The cached-`matchMedia` lever README's Run 40 block describes.

No redaction was needed in any of the three patches — none contains a board address, hostname or
credential (checked by grep for every KNOWN value, 0 hits).

### Third-pass summary

- **Recovered:** the actually-used 2-arg `run-phase.sh` variant (1 file), and the frontend patches for
  Runs 37, 39, 40 (3 files, one of the three spanning two source files).
- **Reported as fact, not corrected:** the README's Runs 8-13 harness description overstates
  `run-phase.sh`'s reach; the table above states precisely which four runs it doesn't cover and what
  each actually used instead.
- **Confidence:** HIGH throughout — every driver-to-run mapping and every patch hunk traces to an
  exact transcript line, and the two genuine retries found (Run 9's rejected first attempt; Run 39's
  failed first Edit) are unambiguous discards, not judgement calls between two live candidates.
