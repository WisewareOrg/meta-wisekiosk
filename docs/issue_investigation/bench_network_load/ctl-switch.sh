#!/bin/bash
# rule switch: $1 = slot number to boot next (0 or 1); mark-active and read back in the same session. No reboot here.
echo "== mark-active rootfs.$1 $(date +%T)"
bash ${ORCH:?operator scratch directory}/ctl-ssh.sh "rauc status mark-active rootfs.$1; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT"
