#!/bin/bash
# check-core-pattern.sh <ssh-target> -- read-only: the kernel's core dump handler and whether
# the kiosk service's default ulimit would allow a core file at all.
set -u
T=${1:?ssh-target}
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh
"$KSSH" "$T" 'cat /proc/sys/kernel/core_pattern; ulimit -c'
