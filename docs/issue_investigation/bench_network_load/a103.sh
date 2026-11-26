#!/bin/bash
# rule: net-analyst's cipher A/B/A, run unchanged, with the K-ccache fill overlap printed before and after.
O=${ORCH:?operator scratch directory}; D=${OUT:?output directory}
ov() { echo "$(date +%T) K-ccache fill: k4q.log: $(tail -1 $O/k4q.log); kas containers up: $(docker ps -q --filter ancestor=ghcr.io/siemens/kas/kas:5.4 | wc -l); Afill log last task: $(grep -o 'Running task [0-9]* of [0-9]* ([^)]*)' $O/kccache-Afill.log 2>/dev/null | tail -1 | sed 's#.*recipes-kernel/linux/##')"; }
echo "$(date +%T) rule start" >> $O/netread-chain.log
B=$(ov)
bash $D/tst008-cipher-aba.sh root@${BENCH:?the bench board address} $D/a103-cipher-aba.txt; rc=$?
A=$(ov)
sed -i "1i == overlap (bench-op-2): before: $B\n== overlap (bench-op-2): after:  $A\n== script rc $rc" $D/a103-cipher-aba.txt
echo "$(date +%T) rule ended rc $rc; counted: $(grep -o "counted '[^']*'" $D/a103-cipher-aba.txt | tr '\n' ' ')" >> $O/netread-chain.log
