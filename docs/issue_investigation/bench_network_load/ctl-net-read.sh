#!/bin/bash
# tst008-control.md (rule) reads, before and after each TST008, outside the calls. $1 = label.
echo "== net read $1 $(date +%T)"
bash ${ORCH:?operator scratch directory}/ctl-ssh.sh 'cat /proc/net/wireless; ip -s link show wlan0; cat /proc/net/softnet_stat | head -1; cat /proc/loadavg; grep usage_usec /sys/fs/cgroup/system.slice/system-sshd.slice/cpu.stat; cut -d" " -f1 /proc/uptime; grep meta-wisekiosk /etc/buildinfo'
