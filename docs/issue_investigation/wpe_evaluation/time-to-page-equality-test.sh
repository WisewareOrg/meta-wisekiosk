#!/usr/bin/env bash
# Equality test: measure-page.sh (WPE, journalctl TITLE) and time-to-page-x.sh (X baseline,
# xwininfo/xprop) must compute the IDENTICAL time-to-page and the IDENTICAL SUSPECT verdict
# from the identical underlying facts -- the whole point of running one baseline and one
# candidate harness side by side is that a difference between their NUMBERS is a difference
# in the BOARD, never a difference in how the two scripts do arithmetic.
#
#   docs/issue_investigation/wpe_evaluation/time-to-page-equality-test.sh
#
# Neither script has a sourceable pure function -- each is read-the-journal-or-X,
# compute, print -- so this reaches both SHIPPED scripts as subprocesses, with every
# external command they call (date, cut, sleep, journalctl, xwininfo, xprop) stubbed on
# PATH to return the SAME fixed facts to both: a title epoch (the beacon's "T <epoch_ms>"),
# a date-at-rollover sequence (first call returns S, every later call returns S+1 --
# simulating the "spin until the wall clock rolls over" loop without a real spin), a fixed
# /proc/uptime reading (via a stubbed `cut`, since /proc/uptime is a file path, not a
# command, and can't be stubbed any other way), and journalctl's clock-step lines.
#
# Run TWICE, once per BOTH-DIRECTIONS case (measure-first discipline: a check that cannot
# come out both ways checks nothing):
#   LATE  a clock-step line stamped AFTER the computed time-to-page -> SUSPECT in both.
#   EARLY a clock-step line stamped BEFORE it -> SUSPECT in NEITHER.
# Each case asserts boot_epoch_ms, RESULT_time_to_page_s and the SUSPECT line's presence/
# absence are byte-identical between the two scripts' outputs.
set -uo pipefail

HERE=$(dirname "$0")
MEASURE_PAGE="$HERE/../../../meta-wisekiosk/recipes-core/kiosk-bootprof/files/measure-page.sh"
TTP_X="$HERE/time-to-page-x.sh"

pass=0
fail=0

# Fixed facts, shared by both scripts and both cases.
TTP_S=1700000000                 # the wall-clock second `date +%s` first reads, pre-rollover
TTP_UP='200.50'                  # /proc/uptime's second field at the rollover instant
TTP_EPOCH_MS=1699999820500       # the beacon's "T <epoch_ms>" title
# BOOT = (S+1)*1000 - UP*1000 = 1700000001000 - 200500 = 1699999800500
# TTP  = (EPOCH_MS - BOOT) / 1000 = 20000 / 1000 = 20.00 s
WANT_BOOT=1699999800500
WANT_TTP='20.00'

LATE_STEP='[   25.123456] Time has been changed'           # 25.12 > 20.00 -> SUSPECT
EARLY_STEP='[    5.123456] Initial clock synchronization'  # 5.12 < 20.00 -> not SUSPECT

make_stub_bin() {
    local dir=$1
    mkdir -p "$dir"

    cat > "$dir/date" << 'EOF'
#!/bin/sh
# Only "+%s" is used by either script. First call in a run returns $TTP_S (the second
# BEFORE the rollover); every call after returns $TTP_S + 1 -- the rollover the "spin
# until date +%s changes" loop is waiting for, without a real spin.
n=0
[ -f "$TTP_STATE/date_calls" ] && n=$(cat "$TTP_STATE/date_calls")
n=$((n + 1))
echo "$n" > "$TTP_STATE/date_calls"
if [ "$n" -le 1 ]; then
    echo "$TTP_S"
else
    echo "$((TTP_S + 1))"
fi
EOF

    cat > "$dir/cut" << 'EOF'
#!/bin/sh
# Only used here on /proc/uptime. The two call sites are distinguished by delimiter alone:
# "-d." (NOW, gating the pre-read sleep) always reads as already past READ_AT, so neither
# script's real `sleep $((READ_AT - NOW))` ever fires; "-d " (UP, the rollover-instant
# reading used in the BOOT arithmetic) returns the fixed fact.
case "$1" in
    -d.) echo 999999 ;;
    "-d ") echo "$TTP_UP" ;;
    *) echo "cut stub: unexpected args: $*" >&2; exit 1 ;;
esac
EOF

    cat > "$dir/sleep" << 'EOF'
#!/bin/sh
# Never actually sleeps -- NOW/TITLE stubs above mean nothing should call this for real,
# but a test must not hang if something does.
exit 0
EOF

    cat > "$dir/journalctl" << 'EOF'
#!/bin/sh
# measure-page.sh's two call shapes: "-u kiosk -o cat" (find the TITLE line) and
# "-o short-monotonic" (find clock-step lines).
case "$*" in
    *"-u kiosk"*) printf 'TITLE T %s\n' "$TTP_EPOCH_MS" ;;
    *) [ -n "${TTP_STEP_LINE:-}" ] && printf '%s\n' "$TTP_STEP_LINE" ;;
esac
EOF

    cat > "$dir/xwininfo" << 'EOF'
#!/bin/sh
# One override-redirect-looking window, matching the awk '/^ +0x/ { print $1 }' filter.
printf '   0x1234567 "test": ()  10x10+0+0  +0+0\n'
EOF

    cat > "$dir/xprop" << 'EOF'
#!/bin/sh
printf 'WM_NAME(STRING) = "T %s"\n' "$TTP_EPOCH_MS"
EOF

    # journalctl's short-monotonic clock-step search runs unconditionally in BOTH scripts,
    # X baseline included -- give it the same stub so both read identical "facts".
    chmod +x "$dir"/date "$dir"/cut "$dir"/sleep "$dir"/journalctl "$dir"/xwininfo "$dir"/xprop
}

# run <script> -- returns its stdout with the stub env wired in.
run() {
    local script=$1
    env -i PATH="$STUBBIN:$PATH" \
        TTP_S="$TTP_S" TTP_UP="$TTP_UP" TTP_EPOCH_MS="$TTP_EPOCH_MS" \
        TTP_STEP_LINE="${TTP_STEP_LINE:-}" TTP_STATE="$STATE" \
        sh "$script" 115
}

field() {
    # field <output> <label> -- the value after "label:" or "label_s:", trimmed.
    printf '%s\n' "$1" | sed -n "s/^$2:[[:space:]]*//p"
}

check_case() {
    local name=$1 want_suspect=$2
    STATE=$(mktemp -d); mkdir -p "$STATE"
    local out_measure out_x

    rm -f "$STATE/date_calls"
    out_measure=$(run "$MEASURE_PAGE")
    rm -f "$STATE/date_calls"
    out_x=$(run "$TTP_X")
    rm -rf "$STATE"

    local boot_m boot_x ttp_m ttp_x susp_m susp_x
    boot_m=$(field "$out_measure" "boot_epoch_ms")
    boot_x=$(field "$out_x" "boot_epoch_ms")
    ttp_m=$(field "$out_measure" "RESULT_time_to_page_s")
    ttp_x=$(field "$out_x" "RESULT_time_to_page_s")
    susp_m=$([[ "$out_measure" == *"SUSPECT:"* ]] && echo yes || echo no)
    susp_x=$([[ "$out_x" == *"SUSPECT:"* ]] && echo yes || echo no)

    local ok=1
    if [ "$boot_m" != "$WANT_BOOT" ] || [ "$boot_x" != "$WANT_BOOT" ]; then ok=0; fi
    if [ "$ttp_m" != "$WANT_TTP" ] || [ "$ttp_x" != "$WANT_TTP" ]; then ok=0; fi
    if [ "$susp_m" != "$want_suspect" ] || [ "$susp_x" != "$want_suspect" ]; then ok=0; fi

    if [ "$ok" -eq 1 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name" >&2
        echo "      boot_epoch_ms   want=$WANT_BOOT  measure-page=$boot_m  time-to-page-x=$boot_x" >&2
        echo "      time_to_page_s  want=$WANT_TTP   measure-page=$ttp_m  time-to-page-x=$ttp_x" >&2
        echo "      SUSPECT         want=$want_suspect  measure-page=$susp_m  time-to-page-x=$susp_x" >&2
    fi
}

STUBBIN=$(mktemp -d)
make_stub_bin "$STUBBIN"
trap 'rm -rf "$STUBBIN"' EXIT

TTP_STEP_LINE="$LATE_STEP"  check_case "a clock step AFTER the beacon -> SUSPECT in both" yes
TTP_STEP_LINE="$EARLY_STEP" check_case "a clock step BEFORE the beacon -> SUSPECT in neither" no

echo "time-to-page-equality: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
