#!/bin/bash
# rule: step 3 rerun once, right after step 5, beside Afill; dropped if not ended by 21:10.
O=${ORCH:?operator scratch directory}
until grep -q "steps 4-5 ended" $O/netread-chain.log; do sleep 3; done
[ "$(date +%H%M%S)" -lt 210800 ] || { echo "$(date +%T) step 3 rerun DROPPED (too late for 21:10)" >> $O/netread-chain.log; exit 0; }
echo "$(date +%T) step 3 rerun start (rule)" >> $O/netread-chain.log
bash $O/netread.sh 3
echo "$(date +%T) step 3 rerun ended: $(grep -E 'counts \(rule\)|VOID, no retry' ${OUT:?output directory}/bench-net-read.txt | tail -1)" >> $O/netread-chain.log
