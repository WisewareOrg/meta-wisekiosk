#!/bin/bash
# A102: step 3 rerun once, right after step 5, beside Afill; dropped if not ended by 21:10.
O=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/78a61228-d84d-4353-990b-bf04f02f1d7b/scratchpad/orch
until grep -q "steps 4-5 ended" $O/netread-chain.log; do sleep 3; done
[ "$(date +%H%M%S)" -lt 210800 ] || { echo "$(date +%T) step 3 rerun DROPPED (too late for 21:10)" >> $O/netread-chain.log; exit 0; }
echo "$(date +%T) step 3 rerun start (A102)" >> $O/netread-chain.log
bash $O/netread.sh 3
echo "$(date +%T) step 3 rerun ended: $(grep -E 'counts \(A102\)|VOID, no retry' /home/tjwise/.claude/deliverables/78a61228-d84d-4353-990b-bf04f02f1d7b/bench-net-read.txt | tail -1)" >> $O/netread-chain.log
