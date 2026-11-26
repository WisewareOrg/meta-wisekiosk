#!/bin/bash
# Network read steps 1-3 the moment arm A's run is over and no kas container is up (architect via timekeeper); refuses with a run on the bench.
O=${ORCH:?operator scratch directory}
L=$O/netread-chain.log
say() { echo "$(date +%T) $*" >> $L; }
until [ -f $O/kccache-A.done ] && [ -z "$(docker ps -q --filter ancestor=ghcr.io/siemens/kas/kas:5.4)" ]; do sleep 3; done
s=$(systemctl --user is-active bench-run.service); p=$(systemctl --user is-active bench-run@prod.service)
case "$s" in activating|active) say "STOP: bench-run $s"; echo stopped > $O/netread-chain.done; exit 1;; esac
say "steps 1-3 start (arm A done: $(cat $O/kccache-A.done); containers: $(docker ps --format '{{.Image}}' | tr '\n' ' '); prod $p)"
bash $O/netread.sh 1 2 3
say "steps 1-3 ended"; echo "ended $(date +%T)" > $O/netread-chain.done
