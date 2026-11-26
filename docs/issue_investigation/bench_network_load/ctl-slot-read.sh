#!/bin/bash
# rule read (before and after each switch): buildinfo, rauc status json, boot variables, boot id. $1 = label
echo "== slot read $1 $(date +%T)"
bash ${ORCH:?operator scratch directory}/ctl-ssh.sh 'grep meta-wisekiosk /etc/buildinfo; rauc status --detailed --output-format=json; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT; cat /proc/sys/kernel/random/boot_id; cat /proc/uptime'
