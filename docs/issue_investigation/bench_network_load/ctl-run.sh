#!/bin/bash
# TST008 control, slot form (rule, rule): B = other slot (afcbaa3) TST008 once; back to X (e0b3363) TST008 twice. Board only, no kas.
S=${ORCH:?operator scratch directory}
D=${OUT:?output directory}
O=$D/tst008-control-reads.txt
L=$S/ctl-run.log
SSH="bash $S/ctl-ssh.sh"
say() { echo "$(date +%T) $*" | tee -a $L >> $O; }
stop() { say "STOP: $*"; echo "stopped" > $S/ctl-run.done; exit 1; }
: > $O; : > $L
tmp=${ORCH:?operator scratch directory}/ctl-tmp.txt
slot_state() { # label -> sets BOOTED (0|1) , OTHER, prints read; checks good
  bash $S/ctl-slot-read.sh "$1" > $tmp; cat $tmp >> $O
  BOOTED=$(python3 - <<PY
import re,json,sys
t=open('$tmp').read()
j=[l for l in t.splitlines() if l.startswith('{')]
d=json.loads(j[0]) if j else {}
b=[list(x.keys())[0] for x in d.get('slots',[]) if list(x.values())[0].get('state')=='booted']
print(b[0].split('.')[-1] if b else '?')
PY
)
  GOOD=$(python3 - <<PY
import json
t=open('$tmp').read()
j=[l for l in t.splitlines() if l.startswith('{')]
d=json.loads(j[0]) if j else {}
st=[ (list(s.values())[0].get('boot_status')) for s in d.get('slots',[]) ]
print(' '.join(str(x) for x in st))
PY
)
  ORDER=$(grep '^BOOT_ORDER=' $tmp | cut -d= -f2 | cut -d' ' -f1)
  COMMIT=$(grep 'meta-wisekiosk' $tmp | sed 's/.*HEAD:\([0-9a-f]\{7\}\).*/\1/')
  UP=$(tail -1 $tmp | cut -d' ' -f1 | cut -d. -f1)
  say "slot read '$1': booted rootfs.$BOOTED order-head $ORDER commit $COMMIT slot states [$GOOD] uptime ${UP}s"
}
wait_up() { # wait for ssh and uptime >= 200 s, max 12 min
  t0=$(date +%s); while true; do
    u=$($SSH 'cut -d" " -f1 /proc/uptime' 2>/dev/null | tail -1 | cut -d. -f1)
    nb=$($SSH 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null | tail -1)
    if [[ "$u" =~ ^[0-9]+$ ]] && [ "$u" -ge 200 ] && [ -n "$nb" ] && [ "$nb" != "$OLDBOOT" ]; then say "board up on a new boot (${nb:0:8}), uptime ${u}s"; return 0; fi
    [ $(( $(date +%s) - t0 )) -gt 900 ] && { say "no ssh answer or uptime under 200 s after 15 min: plug cut is architect's rule (one, by the plug); stopping"; return 1; }
    sleep 10; done; }
tst008() { # label
  bash $S/ctl-net-read.sh "before $1" >> $O
  cd ~/WiseBenchManager
  ids=$(python3 -c "import sqlite3;c=sqlite3.connect('file:${BENCH_MANAGER:?bench runner directory}/records/queue.db?mode=ro',uri=True);print(len(c.execute('select id from queue').fetchall()))")
  [ "$ids" = 0 ] || stop "hand queue not empty before $1 ($ids)"
  .venv/bin/bench test -C ${REPO:?this repository checkout} e0b3363 --skip-build -- -k test_sustained_network_load 2>&1 | tail -1 | tee -a $L >> $O
  systemctl --user start --no-block bench-run.service; sleep 5
  while [ "$(systemctl --user is-active bench-run.service)" = activating ] || [ "$(systemctl --user is-active bench-run.service)" = active ]; do sleep 3; done
  R=$(ls -td ~/WiseBenchManager/records/2026* | head -1)
  say "TST008 $1: record $(basename $R): $(grep -E 'run (passed|failed|error)' $R/bench.log | cut -c1-80); $(python3 - <<PY
import json
for l in open('$R/target_suite/report.jsonl'):
    e=json.loads(l)
    if e.get('\$report_type')=='TestReport' and e.get('when')=='call':
        p=dict(map(tuple,e['user_properties'])); print(e['outcome'], round(e['duration'],1), {k:str(v)[:60] for k,v in p.items() if k in ('requirement','kernel','uptime_s','longest_off_s','boot_id')})
PY
)"
  say "TST008 $1 failure text: $(grep -m1 AssertionError $R/bench.log | cut -c1-220)"
  bash $S/ctl-net-read.sh "after $1" >> $O
}
switch_to() { # slot number; verify read-back
  bash $S/ctl-switch.sh $1 > $tmp; cat $tmp >> $O
  hd=$(grep '^BOOT_ORDER=' $tmp | cut -d= -f2 | cut -d' ' -f1); want=$([ $1 = 0 ] && echo A || echo B)
  cnt=$(grep "^BOOT_${want}_LEFT=" $tmp | cut -d= -f2)
  if [ "$hd" != "$want" ] || [ "$cnt" != 3 ]; then say "read-back wrong (order head $hd, counter $cnt): undoing with mark-active rootfs.$2"; bash $S/ctl-switch.sh $2 >> $O; stop "switch read-back wrong"; fi
  say "switch to rootfs.$1 read back: order head $hd counter $cnt"
}
OLDBOOT=""
reboot_board() { OLDBOOT=$($SSH 'cat /proc/sys/kernel/random/boot_id' | tail -1); $SSH 'systemctl reboot' >/dev/null 2>&1; say "systemctl reboot sent (old boot id ${OLDBOOT:0:8})"; sleep 40; }
# --- start
slot_state "before B"
X=$BOOTED; Y=$([ "$X" = 0 ] && echo 1 || echo 0)
[ "$COMMIT" = e0b3363 ] || stop "booted commit is $COMMIT, expected e0b3363"
for g in $GOOD; do [ "$g" = good ] || stop "a slot is not good: [$GOOD]"; done
[ "$ORDER" = "$([ $X = 0 ] && echo A || echo B)" ] || stop "BOOT_ORDER does not start with the booted slot"
say "X=rootfs.$X (e0b3363), Y=rootfs.$Y"
switch_to $Y $X
reboot_board; wait_up || stop "B did not come up"
slot_state "after B boot"
if [ "$COMMIT" != afcbaa3 ] || [ "$BOOTED" != "$Y" ]; then say "B arm VOID: commit $COMMIT booted rootfs.$BOOTED (expected afcbaa3 on rootfs.$Y); putting the board back to X"; switch_to $X $Y; reboot_board; wait_up; slot_state "after return (void B)"; stop "B void"; fi
$SSH 'sha256sum /usr/lib/modules/6.12.93/kernel/kernel/configs.ko.xz; cat /usr/lib/modules/6.12.93/kernel/kernel/configs.ko.xz' > /dev/null 2>&1
$SSH 'cat /usr/lib/modules/6.12.93/kernel/kernel/configs.ko.xz' > $D/tst008-control-B-configs.ko.xz 2>/dev/null
say "B configs.ko.xz copied: $(sha256sum $D/tst008-control-B-configs.ko.xz | cut -c1-16) ($(stat -c %s $D/tst008-control-B-configs.ko.xz) B)"
tst008 "B (afcbaa3)"
slot_state "before return"
switch_to $X $Y
reboot_board; wait_up || stop "return did not come up"
slot_state "after return"
if [ "$COMMIT" != e0b3363 ] || [ "$BOOTED" != "$X" ]; then stop "return not valid: commit $COMMIT booted rootfs.$BOOTED"; fi
say "return valid: e0b3363 on rootfs.$X, order head $ORDER"
tst008 "A return 1"
tst008 "A return 2"
slot_state "end state"
echo ended > $S/ctl-run.done; say "control ended"
