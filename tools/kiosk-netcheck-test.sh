#!/usr/bin/env bash
# Self-test for kiosk-netcheck's restart and proof decisions.
#
#   tools/kiosk-netcheck-test.sh
#
# Runs the SHIPPED script, meta-wisekiosk/recipes-core/kiosk-netcheck/files/kiosk-netcheck,
# with only its /data and /proc paths pointed into a scratch directory, and the board's
# commands (rauc, ping, fw_printenv, systemctl) replaced by stubs on PATH. The rewrite is
# checked: a path the script gains that the rewrite does not cover fails the run instead
# of reaching the host's real /data.
#
# BOTH DIRECTIONS, deliberately. A wrong restart is a boot loop on the wall unit, and a
# missing one leaves an image that cannot reach the network booted, so each case pins
# whether the boot restarts, what it exits with, and what proof it leaves.
#
# TO WATCH THIS FAIL -- before trusting a green run: point $shipped at a scratch copy of the
# script with one condition removed. Measured:
#   * drop `! proven "$booted_name" "$booted_hash"` from the restart: "no-LAN, booted proven"
#   * replace `proven "$fallback" "$fallback_hash"` with `true`: "no-LAN, fallback unproven"
#     and "no-LAN, fallback proof stale"
#   * replace the /proc/mounts check with `true`: "LAN, /data not mounted"
#
# Exit: 0 every case passed; 1 a case failed or the script's paths changed.
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
shipped=$root/meta-wisekiosk/recipes-core/kiosk-netcheck/files/kiosk-netcheck
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT

script=$scratch/kiosk-netcheck
sed -e "s|/data/|$scratch/data/|g" -e "s|/data |$scratch/data |g" \
    -e "s|/proc/uptime|$scratch/uptime|g" -e "s|/proc/mounts|$scratch/mounts|g" \
    "$shipped" > "$script"
# The rewrite reaches every /data and /proc the script names.
if grep -n -E '(^|[^a-z])/(data|proc)[/ ]' "$script" | grep -v -F "$scratch" > "$scratch/unrewritten"; then
    echo "FAIL the script names a /data or /proc path the rewrite does not cover:"
    cat "$scratch/unrewritten"
    exit 1
fi

mkdir -p "$scratch/bin"
cat > "$scratch/bin/rauc" <<EOF
#!/bin/sh
[ -e "$scratch/rauc.fails" ] && exit 1
cat "$scratch/rauc.out"
EOF
cat > "$scratch/bin/ping" <<EOF
#!/bin/sh
[ -e "$scratch/lan" ]
EOF
cat > "$scratch/bin/fw_printenv" <<'EOF'
#!/bin/sh
echo "BOOT_ORDER=B A"
EOF
cat > "$scratch/bin/systemctl" <<EOF
#!/bin/sh
echo "\$*" >> "$scratch/systemctl.log"
EOF
chmod +x "$scratch/bin/"*

pass=0
fail=0

# setup LAN MOUNTED BOOTED_HASH BOOTED_PROOF FALLBACK_STATUS FALLBACK_HASH FALLBACK_PROOF RAUC
#   LAN, MOUNTED and RAUC are yes/no; a proof of "-" is no proof file. The booted slot is A.
setup() {
    rm -rf "$scratch/data" "$scratch/lan" "$scratch/rauc.fails" "$scratch/systemctl.log"
    mkdir -p "$scratch/data/kiosk-netcheck"
    printf 'DEADLINE=0\nTARGET=gateway\n' > "$scratch/data/kiosk-netcheck.conf"
    echo "100.00 50.00" > "$scratch/uptime"
    [ "$1" = yes ] && touch "$scratch/lan"
    if [ "$2" = yes ]; then
        echo "/dev/mmcblk0p4 $scratch/data ext4 rw 0 0" > "$scratch/mounts"
    else
        echo "/dev/root / ext4 rw 0 0" > "$scratch/mounts"
    fi
    [ "$4" = - ] || printf '%s\n' "$4" > "$scratch/data/kiosk-netcheck/reached.A"
    [ "$7" = - ] || printf '%s\n' "$7" > "$scratch/data/kiosk-netcheck/reached.B"
    [ "$8" = yes ] || touch "$scratch/rauc.fails"
    cat > "$scratch/rauc.out" <<EOF
RAUC_SLOTS='1 2'
RAUC_SLOT_STATE_1='booted'
RAUC_SLOT_BOOT_STATUS_1='good'
RAUC_SLOT_BOOTNAME_1='A'
RAUC_SLOT_STATUS_BUNDLE_HASH_1='$3'
RAUC_SLOT_STATE_2='inactive'
RAUC_SLOT_BOOT_STATUS_2='$5'
RAUC_SLOT_BOOTNAME_2='B'
RAUC_SLOT_STATUS_BUNDLE_HASH_2='$6'
EOF
}

# check NAME EXIT RESTARTS PROOF_A -- runs the script and compares its exit code, whether it
#   asked systemctl to reboot (yes/no), and slot A's proof afterwards ("-" for none).
check() {
    local name=$1 want_rc=$2 want_restart=$3 want_proof=$4 rc restarted proof
    PATH="$scratch/bin:$PATH" sh "$script" > "$scratch/out" 2>&1
    rc=$?
    restarted=no
    grep -q reboot "$scratch/systemctl.log" 2> /dev/null && restarted=yes
    proof=-
    [ -e "$scratch/data/kiosk-netcheck/reached.A" ] && proof=$(cat "$scratch/data/kiosk-netcheck/reached.A")
    if [ "$rc" = "$want_rc" ] && [ "$restarted" = "$want_restart" ] && [ "$proof" = "$want_proof" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL $name: exit $rc restart $restarted proof $proof; want exit $want_rc restart $want_restart proof $want_proof"
        sed 's/^/    /' "$scratch/out"
    fi
}

#     LAN MOUNTED A-HASH A-PROOF B-STATUS B-HASH B-PROOF RAUC
setup yes yes  hA     -       good     hB     hB      yes; check "LAN, booted unproven: proof written" 0 no hA
setup yes yes  hA     hA      good     hB     hB      yes; check "LAN, booted proven: proof kept" 0 no hA
setup yes yes  hA     old     good     hB     hB      yes; check "LAN, stale proof: proof replaced" 0 no hA
setup yes yes  hA     -       good     hB     hB      no;  check "LAN, rauc unreadable: nothing recorded" 0 no -
setup yes no   hA     -       good     hB     hB      yes; check "LAN, /data not mounted: nothing recorded" 0 no -
setup yes yes  ''     -       good     hB     hB      yes; check "LAN, booted hash empty: nothing recorded" 0 no -
setup no  yes  hA     -       good     hB     hB      yes; check "no-LAN, booted unproven, fallback proven: restart" 1 yes -
setup no  yes  hA     hA      good     hB     hB      yes; check "no-LAN, booted proven: withhold, no restart" 1 no hA
setup no  yes  hA     -       good     hB     -       yes; check "no-LAN, fallback unproven: withhold, no restart" 1 no -
setup no  yes  hA     -       good     hB     old     yes; check "no-LAN, fallback proof stale: withhold, no restart" 1 no -
setup no  yes  hA     -       good     hB     hB      no;  check "no-LAN, rauc unreadable: withhold, no restart" 1 no -
setup no  yes  hA     -       bad      hB     hB      yes; check "no-LAN, no good fallback: mark good, no restart" 0 no -

echo "pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
