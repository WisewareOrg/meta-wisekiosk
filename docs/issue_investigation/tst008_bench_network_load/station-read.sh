#!/bin/bash
# T74 / net-analyst: one ssh outside the TST008 call: station rates, loadavg, uptime. usage: station-read.sh LABEL
D=/home/tjwise/.claude/deliverables/78a61228-d84d-4353-990b-bf04f02f1d7b; O=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/78a61228-d84d-4353-990b-bf04f02f1d7b/scratchpad/orch
R=$(ls -td /home/tjwise/WiseBenchManager/records/2026* | head -1)
{ echo "== $1 $(date +%T.%N | cut -c1-12) EST; record $(basename $R) last line: $(grep '^bench:' $R/bench.log | tail -1 | cut -c1-110)"
  bash $O/ctl-ssh.sh "iw dev wlan0 station dump | grep -E 'rx bitrate|tx bitrate|tx failed|signal:'; cat /proc/loadavg; cut -d' ' -f1 /proc/uptime" | sed -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/<mac>/g'; } >> $D/tst008-6a34d6f-station.txt
