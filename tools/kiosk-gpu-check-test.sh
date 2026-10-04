#!/usr/bin/env bash
# Exit: 0 all checks pass; 1 one or more failed.
set -uo pipefail

HERE=$(dirname "$0")
# shellcheck source=tools/kiosk-gpu-check.sh
KIOSK_GPU_CHECK_LIB=1 . "$HERE/kiosk-gpu-check.sh"

pass=0
fail=0

check() {
    local name=$1 want=$2 probe=$3 got
    gpu_verdict "$probe" > /dev/null 2>&1
    got=$?
    if [ "$got" -eq "$want" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name: expected rc=$want, got rc=$got" >&2
    fi
}

MEM='mem CmaTotal:         131072 kB
mem CmaFree:           98304 kB
drm card0 present'

check "vc4 hardware" 0 "proc surf pid=311 drifd=0 drv=none
proc WebKitWebProces pid=340 drifd=2 drv=v3d_dri.so vc4_dri.so
$MEM"

check "vc4, renderer only" 0 "proc WebKitWebProces pid=340 drifd=1 drv=vc4_dri.so
$MEM"

check "ten dri fds pass" 0 "proc WebKitWebProces pid=340 drifd=10 drv=vc4_dri.so
$MEM"

check "swrast-only fails" 1 "proc WebKitWebProces pid=340 drifd=1 drv=swrast_dri.so
$MEM"

check "kms-swrast-only fails" 1 "proc WebKitWebProces pid=340 drifd=1 drv=kms_swrast_dri.so
$MEM"

check "no dri fd fails" 1 "proc surf pid=311 drifd=0 drv=none
proc WebKitWebProces pid=340 drifd=0 drv=none
mem CmaTotal:          65536 kB
mem CmaFree:           61440 kB
drm card0 absent"

check "no browser process is rc2" 2 "$MEM"
check "empty probe is rc2" 2 ""

check "grep -o missing is rc2" 2 "cap grep_o=0
proc WebKitWebProces pid=340 drifd=1 drv=none
$MEM"

check "unreadable fd dir is rc2" 2 "cap grep_o=1
proc WebKitWebProces pid=340 drifd=? drv=vc4_dri.so
$MEM"

check "unreadable maps is rc2" 2 "cap grep_o=1
proc WebKitWebProces pid=340 drifd=1 drv=?
$MEM"

check "cap grep_o=1 with vc4 passes" 0 "cap grep_o=1
proc WebKitWebProces pid=340 drifd=2 drv=vc4_dri.so
$MEM"

check "fd and driver in DIFFERENT processes fails" 1 "proc surf pid=311 drifd=1 drv=swrast_dri.so
proc WebKitWebProces pid=340 drifd=0 drv=vc4_dri.so
$MEM"

check "mixed vc4+swrast passes" 0 "proc surf pid=311 drifd=1 drv=swrast_dri.so
proc WebKitWebProces pid=340 drifd=2 drv=v3d_dri.so
$MEM"

TOOL="$HERE/kiosk-gpu-check.sh"
emitter=$(sed -n '/^PROBE=/,/^REMOTE$/p' "$TOOL")
verdict=$(sed -n '/^gpu_verdict()/,/^}$/p' "$TOOL")
sentinel_pair() {
    local name=$1 emit=$2 read=$3 e r
    e=$(printf '%s\n' "$emitter" | grep -cF "$emit")
    r=$(printf '%s\n' "$verdict" | grep -cE "$read")
    if [ "$e" -gt 0 ] && [ "$r" -gt 0 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  sentinel $name out of sync: emitter=$e verdict=$r" >&2
    fi
}
sentinel_pair "unreadable-fd"   'dri="?"'       'drifd=[?\\]'
sentinel_pair "unreadable-maps" 'drv="?"'       'drv=[?\\]'
sentinel_pair "grep-o-capability" 'cap grep_o=' 'cap grep_o='

# #185 W2 ruling 2026-10-04: the device-side process-family match (WebKit/surf's era) moves
# to WPEWebProcess|WPENetworkProcess|cog, defined ONCE host-side as KIOSK_BROWSER_PROCS and
# interpolated into the remote heredoc -- not hardcoded a second time there, which is
# exactly the kind of two-sides-drift the sentinel_pair checks above exist to catch for
# every other field this tool emits and reads.
if [ "${KIOSK_BROWSER_PROCS:-}" = 'WPEWebProcess|WPENetworkProcess|cog' ]; then
    pass=$((pass + 1))
else
    fail=$((fail + 1))
    echo "FAIL  KIOSK_BROWSER_PROCS: want 'WPEWebProcess|WPENetworkProcess|cog', got '${KIOSK_BROWSER_PROCS:-}'" >&2
fi

if [ "$(printf '%s\n' "$emitter" | grep -cF '$KIOSK_BROWSER_PROCS')" -gt 0 ]; then
    pass=$((pass + 1))
else
    fail=$((fail + 1))
    echo 'FAIL  the remote heredoc does not reference $KIOSK_BROWSER_PROCS -- the pattern' >&2
    echo "      is hardcoded a second time there instead of interpolated once" >&2
fi

"$HERE/kiosk-gpu-check.sh" > /dev/null 2>&1
rc=$?
if [ $rc -eq 2 ]; then pass=$((pass + 1)); else
    fail=$((fail + 1)); echo "FAIL  no argument: expected rc=2, got rc=$rc" >&2; fi

"$HERE/kiosk-gpu-check.sh" "" > /dev/null 2>&1
rc=$?
if [ $rc -eq 2 ]; then pass=$((pass + 1)); else
    fail=$((fail + 1)); echo "FAIL  empty host: expected rc=2, got rc=$rc" >&2; fi

"$HERE/kiosk-gpu-check.sh" root@example --bogus > /dev/null 2>&1
rc=$?
if [ $rc -eq 2 ]; then pass=$((pass + 1)); else
    fail=$((fail + 1)); echo "FAIL  bad flag: expected rc=2, got rc=$rc" >&2; fi

echo "kiosk-gpu-check: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
