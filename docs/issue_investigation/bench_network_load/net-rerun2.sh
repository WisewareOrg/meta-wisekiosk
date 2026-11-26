#!/bin/bash
# rule rerun (timekeeper order): after the rate track ends: before read (finished before queueing) -> queue 6a34d6f --skip-build TST008 (behind the proof job) -> after the proof job ends, start once -> nothing read in the call -> after read after the run line.
O=${ORCH:?operator scratch directory}
L=$O/tst008-rt.log; say() { echo "$(date +%T) $*" >> $L; }
active() { local s; s=$(systemctl --user is-active bench-run.service); [ "$s" = activating ] || [ "$s" = active ]; }
qids() { python3 -c "import sqlite3;c=sqlite3.connect('file:${BENCH_MANAGER:?bench runner directory}/records/queue.db?mode=ro',uri=True);print(' '.join(str(r[0]) for r in c.execute('select id from queue order by id')))"; }
ov() { echo "kas containers $(docker ps -q --filter ancestor=ghcr.io/siemens/kas/kas:5.4 | wc -l) ($(docker ps --format '{{.Names}}' | tr '\n' ' '))"; }
until [ -f $O/ratetrack.done ]; do sleep 2; done
[ "$(date +%H%M%S)" -lt 211500 ] || { say "TST008 rerun DROPPED (too late to end well before 21:28)"; exit 0; }
q0=$(qids); [ -z "$q0" ] || { say "STOP: queue not empty before queueing the rerun: $q0"; exit 1; }
[ -f ${BENCH_MANAGER:?bench runner directory}/records/DISABLED ] && { say "STOP: DISABLED"; exit 1; }
bash $O/station-read.sh "RERUN before (finished before queueing)"; say "rerun before-read done"
q=$(cd ${BENCH_MANAGER:?bench runner directory} && .venv/bin/bench test -C ${REPO:?this repository checkout} 6a34d6f --skip-build -- -k test_sustained_network_load 2>&1 | tail -1); say "queued: $q"
[ "$(qids | wc -w)" = 1 ] || { say "STOP: queue after queueing: $(qids)"; exit 1; }
until [ -f $O/proofx.done ]; do sleep 2; done; while active; do sleep 2; done
[ -f ${BENCH_MANAGER:?bench runner directory}/records/DISABLED ] && { say "STOP: DISABLED"; exit 1; }
prev=$(ls -td ${BENCH_MANAGER:?bench runner directory}/records/2026* | head -1)
say "START TST008 rerun (unit started once); beside: $(ov)"; systemctl --user start --no-block bench-run.service
for i in $(seq 1 30); do R=$(ls -td ${BENCH_MANAGER:?bench runner directory}/records/2026* | head -1); [ "$R" != "$prev" ] && break; sleep 2; done
say "rerun record $(basename $R)"
sleep 5; while active; do sleep 2; done
say "END TST008 rerun $(basename $R): $(grep -E '^bench: .* run (passed|failed|error)' $R/bench.log | tail -1 | cut -c1-80); beside at end: $(ov)"
bash $O/station-read.sh "RERUN after (after the run line)"
python3 - "$R" >> $L <<'PY'
import json,sys
R=sys.argv[1]
for l in open(R+'/target_suite/report.jsonl'):
    e=json.loads(l)
    if e.get('$report_type')=='TestReport':
        p=dict(map(tuple,e['user_properties'])) if e['when']=='call' else {}
        print('  ', e['when'], e['outcome'], round(e['duration'],1), {k:str(v)[:70] for k,v in p.items()})
PY
grep -m1 "AssertionError" $R/bench.log | cut -c1-240 | sed 's/^/   /' >> $L
echo done > $O/tst008-rerun.done
