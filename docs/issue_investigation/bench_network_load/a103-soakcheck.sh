#!/bin/bash
# After rule ends: one read-only ssh, soak log line count and last line, appended to a103-cipher-aba.txt (net-analyst, for architect).
O=${ORCH:?operator scratch directory}; D=${OUT:?output directory}
until grep -q "rule ended" $O/netread-chain.log; do sleep 3; done
{ echo; echo "== soak log check (architect) $(date +%T) EST"; bash $O/ctl-ssh.sh 'wc -l /data/kiosk-soak.log; tail -n 1 /data/kiosk-soak.log' | sed -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/<mac>/g; /SSID/d'; } >> $D/a103-cipher-aba.txt
echo "$(date +%T) soak log check appended" >> $O/netread-chain.log
