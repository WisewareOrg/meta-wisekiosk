#!/bin/bash
# A105: net-analyst's rate track after TST008's call and after-reads; dropped if not started by 21:08; killed by its own pid at 21:20 (output partial).
O=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/78a61228-d84d-4353-990b-bf04f02f1d7b/scratchpad/orch; D=/home/tjwise/.claude/deliverables/78a61228-d84d-4353-990b-bf04f02f1d7b
L=$O/tst008-rt.log; say() { echo "$(date +%T) $*" >> $L; }
OUT=$D/rate-track.txt
ov() { echo "Afill: $(tail -1 $O/k4q.log); kas containers $(docker ps -q --filter ancestor=ghcr.io/siemens/kas/kas:5.4 | wc -l); last task $(grep -o 'Running task [0-9]* of [0-9]* ([^)]*)' $O/kccache-Afill.log 2>/dev/null | tail -1 | sed 's#.*recipes-kernel/linux/##')"; }
until [ -f $O/tst008-end.done ]; do sleep 2; done
[ "$(date +%H%M%S)" -lt 210800 ] || { say "rate track DROPPED (not started by 21:08, A105)"; exit 0; }
B=$(ov); say "START rate track (A105); beside: $B"
bash $D/tst008-rate-track.sh root@${BENCH:?the bench board address} $OUT 4 & pid=$!
dl=$(date -d "today 21:20" +%s); part=""
while kill -0 $pid 2>/dev/null; do
  if [ $(date +%s) -ge $dl ]; then part=1; pkill -P $pid; kill $pid; say "21:20: rate track killed by its pid $pid (A105): output PARTIAL"; break; fi
  sleep 2; done
wait $pid 2>/dev/null; rc=$?
A=$(ov)
sed -i "1i == bench-op-2: A105. Overlap: before: $B | after: $A\n== The sampler's top and iw reads every 2 s are a known board load, the same in all four pushes.${part:+\n== PARTIAL: killed by its pid at 21:20 (A105); what was read stands.}" $OUT
say "END rate track rc $rc${part:+ (PARTIAL)}: $(grep -o "counted '[^']*'" $OUT | tr '\n' ' ')"
echo done > $O/ratetrack.done
