#!/bin/bash
# A95 switch: $1 = slot number to boot next (0 or 1); mark-active and read back in the same session. No reboot here.
echo "== mark-active rootfs.$1 $(date +%T)"
bash /tmp/claude-1000/-home-tjwise-meta-wisekiosk/78a61228-d84d-4353-990b-bf04f02f1d7b/scratchpad/orch/ctl-ssh.sh "rauc status mark-active rootfs.$1; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT"
