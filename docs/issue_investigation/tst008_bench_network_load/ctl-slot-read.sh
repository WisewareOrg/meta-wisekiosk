#!/bin/bash
# A95 read (before and after each switch): buildinfo, rauc status json, boot variables, boot id. $1 = label
echo "== slot read $1 $(date +%T)"
bash /tmp/claude-1000/-home-tjwise-meta-wisekiosk/78a61228-d84d-4353-990b-bf04f02f1d7b/scratchpad/orch/ctl-ssh.sh 'grep meta-wisekiosk /etc/buildinfo; rauc status --detailed --output-format=json; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT; cat /proc/sys/kernel/random/boot_id; cat /proc/uptime'
