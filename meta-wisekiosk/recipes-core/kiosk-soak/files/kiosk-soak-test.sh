#!/usr/bin/env bash
# Self-test for kiosk-soak.sh's browser-family predicate.
#
#   meta-wisekiosk/recipes-core/kiosk-soak/files/kiosk-soak-test.sh
#
# A sourceable `is_browser_proc <comm>` predicate selects WPE's browser-family process
# names: true for anything starting "WPE" (WPEWebProcess, WPENetworkProcess,
# WPEGPUProcess) and for exactly "cog"; false for everything else.
#
# Reaches the SHIPPED predicate, not a copy: the tool is sourced with KIOSK_SOAK_LIB=1,
# which must define `is_browser_proc` and return before any device access or sampling --
# the same guard shape as render_verdict/gpu_verdict's KIOSK_*_LIB=1 (tools/
# kiosk-render-check.sh, tools/kiosk-gpu-check.sh).
set -uo pipefail

HERE=$(dirname "$0")
# shellcheck disable=SC1091
KIOSK_SOAK_LIB=1 . "$HERE/kiosk-soak.sh"

pass=0
fail=0

check() {
    local name=$1 want=$2 comm=$3 got
    if is_browser_proc "$comm"; then got=0; else got=1; fi
    if [ "$got" -eq "$want" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name: is_browser_proc('$comm') -> rc=$got, want rc=$want" >&2
    fi
}

# --- true: every WPE-family process name, by prefix -----------------------
check "WPEWebProcess matches"     0 "WPEWebProcess"
check "WPENetworkProcess matches" 0 "WPENetworkProcess"
check "WPEGPUProcess matches"     0 "WPEGPUProcess"
# /proc/<pid>/comm truncates at 15 visible characters (TASK_COMM_LEN=16); a prefix match
# survives that truncation where an exact-name match would not -- "WPENetworkProcess" (17
# chars) truncates to "WPENetworkProce", which still starts with "WPE".
check "a comm truncated to 15 chars still matches (prefix survives truncation)" \
    0 "WPENetworkProce"

# --- true: cog itself, exactly -----------------------------------------
check "cog matches" 0 "cog"

# --- false: the X/GTK-era names, and anything else -------------------------
check "surf does not match"          1 "surf"
check "WebKitWebProcess does not match" 1 "WebKitWebProcess"
check "Xorg does not match"          1 "Xorg"
check "cogctl does not match (named like cog, is not cog)" 1 "cogctl"
check "empty comm does not match"    1 ""

echo "kiosk-soak: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
