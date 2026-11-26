#!/bin/bash
# tst008-control.md (T65c) reads, before and after each TST008, outside the calls. $1 = label.
echo "== net read $1 $(date +%T)"
bash /tmp/claude-1000/-home-tjwise-meta-wisekiosk/78a61228-d84d-4353-990b-bf04f02f1d7b/scratchpad/orch/ctl-ssh.sh 'cat /proc/net/wireless; ip -s link show wlan0; cat /proc/net/softnet_stat | head -1; cat /proc/loadavg; grep usage_usec /sys/fs/cgroup/system.slice/system-sshd.slice/cpu.stat; cut -d" " -f1 /proc/uptime; grep meta-wisekiosk /etc/buildinfo'
