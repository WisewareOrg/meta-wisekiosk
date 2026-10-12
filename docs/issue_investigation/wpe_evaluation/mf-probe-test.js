#!/usr/bin/env node
// Node test for mf-probe.js's region-keyed fever counting and fmax tracking.
//
//   node mf-probe-test.js                                 test the shipped mf-probe.js
//   MF_PROBE_PATH=<path> node mf-probe-test.js             test a different copy
//
// Reaches the SHIPPED probe, never a copy: PROBE_SRC below is read verbatim from disk and
// run with Node's vm module in a sandbox stubbing only what the probe touches (window,
// document, performance, setInterval) -- no line of mf-probe.js is reproduced or
// reimplemented here. setInterval is stubbed to CAPTURE the probe's tick callback instead of
// scheduling it 30s out, so a test can call it as many times as it likes with no real delay.
//
// Rules pinned (mf-probe.js's own header; module-fault payload #185 ruling 2026-10-04):
//   fever counts DISTINCT FAULTED REGIONS: a [data-module-faulted] marker is keyed by the
//   nearest ancestor's [data-region] value (a string, so re-faulting the SAME region never
//   increments fever even via a brand-new DOM element -- e.g. after the framework replaces a
//   faulted node). A marker with no [data-region] ancestor is keyed by the ELEMENT ITSELF
//   (object identity), so two such elements are two distinct entries, and a no-region marker
//   that faults, resets (its element is removed) and re-faults as a NEW element counts AGAIN
//   -- an intentional over-count on the no-region path, not a bug.
//   fmax is the max count of SIMULTANEOUSLY faulted markers across samples, not a running
//   total of distinct faults ever seen.
//
// TO WATCH THIS FAIL -- point MF_PROBE_PATH at a scratch copy restored from before 9833dfc
// (element-keyed fever, no [data-region] concept at all: `if (!seen.has(faulted[i]))
// fever++`). Confirmed (2026-10-04): the same-region-refault and second-region scenarios go
// red there -- each one's markers are built by separate makeElement() calls, so even a
// same-region re-fault is a new, never-before-seen element under identity-keying, and fever
// overcounts (3, not 1 or 2). The no-region and fmax scenarios do NOT distinguish the two
// probes, since that behaviour is unchanged by 9833dfc.
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const PROBE_PATH = process.env.MF_PROBE_PATH || path.join(__dirname, 'mf-probe.js');
const PROBE_SRC = fs.readFileSync(PROBE_PATH, 'utf8');
const MF_PAT = /MF\|t=(\d+)\|f=(\d+)\|fmax=(\d+)\|fever=(\d+)\|u=(\d+)\|umax=(\d+)/;

let fails = 0;
function check(name, cond) {
  console.log(`[${cond ? 'PASS' : 'FAIL'}] ${name}`);
  if (!cond) fails++;
}

// A faulted-marker stub. With a region, .closest('[data-region]') returns an ancestor whose
// dataset.region is that string. Without one, .closest() returns null, same as a real DOM
// element with no matching ancestor.
function makeElement(region) {
  return {
    closest(sel) {
      if (sel === '[data-region]' && region !== undefined) {
        return { dataset: { region } };
      }
      return null;
    },
  };
}

// Runs the real mf-probe.js fresh in its own sandbox and returns tick(faultedEls,
// unavailableCount), which simulates one 30s sample and returns the parsed MF| payload.
function freshProbe() {
  let capturedTick = null;
  let faultedEls = [];
  let unavailableCount = 0;
  let clockMs = 0;

  const sandbox = {
    performance: { now: () => clockMs },
    setInterval: (fn) => { capturedTick = fn; return 1; },
    document: {
      title: '',
      querySelectorAll(sel) {
        if (sel === '[data-module-faulted]') return faultedEls;
        if (sel === '[data-module-unavailable]') return new Array(unavailableCount).fill({});
        throw new Error('unexpected selector: ' + sel);
      },
    },
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(PROBE_SRC, sandbox, { filename: PROBE_PATH });
  if (!capturedTick) throw new Error('mf-probe.js never called setInterval');

  return function tick(nextFaultedEls, nextUnavailableCount) {
    faultedEls = nextFaultedEls || [];
    unavailableCount = nextUnavailableCount || 0;
    clockMs += 30000;
    capturedTick();
    const m = MF_PAT.exec(sandbox.document.title);
    if (!m) throw new Error('title did not carry an MF| payload: ' + sandbox.document.title);
    return { t: +m[1], f: +m[2], fmax: +m[3], fever: +m[4], u: +m[5], umax: +m[6] };
  };
}

function scenario_same_region_refault_does_not_increment() {
  const tick = freshProbe();
  tick([makeElement('A')]);            // tick 1: region A faults -> fever 1
  tick([]);                             // tick 2: reset (marker removed)
  const r = tick([makeElement('A')]);  // tick 3: a NEW element, same region A
  check('same-region re-fault (new element): fever stays 1', r.fever === 1);
}

function scenario_second_region_increments() {
  const tick = freshProbe();
  tick([makeElement('A')]);
  const r = tick([makeElement('A'), makeElement('B')]);
  check('a second region faulting: fever becomes 2', r.fever === 2);
}

function scenario_two_no_region_markers_count_as_two() {
  const tick = freshProbe();
  const r = tick([makeElement(), makeElement()]); // neither has a [data-region] ancestor
  check('two distinct no-region markers: fever == 2', r.fever === 2);
}

function scenario_no_region_fault_reset_refault_counts_twice() {
  const tick = freshProbe();
  tick([makeElement()]);           // tick 1: a no-region marker faults
  tick([]);                         // tick 2: reset (element removed)
  const r = tick([makeElement()]); // tick 3: a NEW no-region element faults
  check('no-region fault/reset/re-fault: fever == 2 (intentional over-count)', r.fever === 2);
}

function scenario_fmax_tracks_simultaneous_not_cumulative() {
  const tick = freshProbe();
  tick([makeElement('A')]);                      // f=1
  tick([]);                                       // f=0
  tick([makeElement('B'), makeElement('C')]);     // f=2, the true simultaneous peak
  const r = tick([makeElement('D')]);             // f=1
  check('fmax tracks the simultaneous peak (2), not a cumulative distinct-fault count',
        r.fmax === 2);
}

scenario_same_region_refault_does_not_increment();
scenario_second_region_increments();
scenario_two_no_region_markers_count_as_two();
scenario_no_region_fault_reset_refault_counts_twice();
scenario_fmax_tracks_simultaneous_not_cumulative();

console.log();
if (fails) {
  console.error(`${fails} check(s) FAILED`);
  process.exit(1);
}
console.log('all checks passed');
