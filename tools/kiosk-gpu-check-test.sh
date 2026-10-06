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

# The device-side process-family match is WPEWebProcess|WPENetworkProcess|WPEGPUProcess|wpe-kiosk
# (WPEGPUProcess: 2.54 spawns it; wpe-kiosk is the launcher, renamed from cog to fit
# comm's 15-character limit), defined ONCE host-side as KIOSK_BROWSER_PROCS and
# interpolated into the remote heredoc -- not hardcoded a second time there, which is
# exactly the kind of two-sides-drift the sentinel_pair checks above exist to catch for
# every other field this tool emits and reads.
if [ "${KIOSK_BROWSER_PROCS:-}" = 'WPEWebProcess|WPENetworkProcess|WPEGPUProcess|wpe-kiosk' ]; then
    pass=$((pass + 1))
else
    fail=$((fail + 1))
    echo "FAIL  KIOSK_BROWSER_PROCS: want 'WPEWebProcess|WPENetworkProcess|WPEGPUProcess|wpe-kiosk', got '${KIOSK_BROWSER_PROCS:-}'" >&2
fi

# shellcheck disable=SC2016
if [ "$(printf '%s\n' "$emitter" | grep -cF '$KIOSK_BROWSER_PROCS')" -gt 0 ]; then
    pass=$((pass + 1))
else
    fail=$((fail + 1))
    # shellcheck disable=SC2016
    echo 'FAIL  the remote heredoc does not reference $KIOSK_BROWSER_PROCS -- the pattern' >&2
    echo "      is hardcoded a second time there instead of interpolated once" >&2
fi

# BEHAVIOURAL, not textual: a case statement cannot use a variable's "|"-joined value as
# alternation (shell parses case's "|" syntactically, before any expansion -- confirmed by
# hand: `case "$x" in $V) ...` with V="a|b" never matches "a" or "b", only the literal
# string "a|b"), so a presence check alone cannot tell a correct wiring from a silently
# broken one. This extracts the SHIPPED KIOSK_BROWSER_PROCS definition and the SHIPPED
# PAT= construction line verbatim from the tool and runs them for real under `sh`
# (busybox-compatible: tr/cut/sed/grep -E only, no bash-only syntax) against synthetic
# /proc comm values -- reaching the real matching mechanism, not a reimplementation of it.
PROCS_LINE=$(grep -m1 '^KIOSK_BROWSER_PROCS=' "$TOOL")
PAT_LINE=$(sed -n '/^PAT=/p' "$TOOL" | head -1)
if [ -z "$PROCS_LINE" ] || [ -z "$PAT_LINE" ]; then
    fail=$((fail + 1))
    echo "FAIL  could not extract KIOSK_BROWSER_PROCS / PAT= from $TOOL -- check anchors" >&2
else
    match_comm() {
        sh -c "$PROCS_LINE; PROCS=\"\$KIOSK_BROWSER_PROCS\"; $PAT_LINE
               printf '%s\n' \"\$1\" | grep -qxE \"\$PAT\"" -- "$1"
    }
    comm_check() {
        local name=$1 want=$2 got
        if match_comm "$name"; then got=0; else got=1; fi
        if [ "$got" -eq "$want" ]; then
            pass=$((pass + 1))
        else
            fail=$((fail + 1))
            echo "FAIL  comm '$name': want match=$([ "$want" -eq 0 ] && echo yes || echo no), got $([ "$got" -eq 0 ] && echo yes || echo no)" >&2
        fi
    }
    comm_check "WPEWebProcess"    0
    comm_check "WPEGPUProcess"    0
    comm_check "wpe-kiosk"        0
    # cog no longer matches: the launcher is renamed to wpe-kiosk.
    comm_check "cog"              1
    # A look-alike must not match: the pattern is anchored (grep -qxE), not a prefix test.
    comm_check "wpe-kiosk-x"      1
    # /proc comm truncates at 15 visible characters; "WPENetworkProcess" (17) is never the
    # literal value a real board reports -- "WPENetworkProce" is, and must match.
    comm_check "WPENetworkProce"  0
    comm_check "surf"             1
    comm_check "cogctl"           1
    comm_check "WebKitWebProcess" 1
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

# --- --capture is removed, not just refused: a plain unknown-argument usage
# error, exactly like --bogus above, naming --capture and carrying none of
# the old WPE-specific "unavailable" wording. webkit://gpu needs desktop GL,
# which the WPE image does not carry, and nothing else on the device exposes
# that data -- there is no WPE path for --capture at all, so it is no longer
# a recognised mode to refuse, just an argument main() does not know.
out=$("$HERE/kiosk-gpu-check.sh" root@example --capture 2>&1)
rc=$?
if [ "$rc" -ne 0 ] && [[ "$out" == *"--capture"* ]] && [[ "$out" != *"unavailable"* ]]; then
    pass=$((pass + 1))
else
    fail=$((fail + 1))
    echo "FAIL  --capture: expected a non-zero usage error naming --capture, with no" >&2
    echo "      WPE-unavailable wording -- got rc=$rc output: $out" >&2
fi

echo "kiosk-gpu-check: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
