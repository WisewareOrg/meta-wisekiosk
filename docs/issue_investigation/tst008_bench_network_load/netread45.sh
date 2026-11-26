#!/bin/bash
# Network read steps 4-5 right after steps 1-3 (proof job dropped); the beside line prints what runs on the host.
O=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/78a61228-d84d-4353-990b-bf04f02f1d7b/scratchpad/orch
until [ -f $O/netread-chain.done ]; do sleep 3; done
s=$(systemctl --user is-active bench-run.service); case "$s" in activating|active) echo "$(date +%T) STOP: bench-run $s" >> $O/netread-chain.log; exit 1;; esac
echo "$(date +%T) steps 4-5 start" >> $O/netread-chain.log
bash $O/netread.sh 4 5
echo "$(date +%T) steps 4-5 ended" >> $O/netread-chain.log
