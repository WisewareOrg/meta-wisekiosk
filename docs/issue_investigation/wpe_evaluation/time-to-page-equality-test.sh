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
#
# PRE-STEP FRAME (#185 ruling 2026-10-04): a step after the beacon with a KNOWN pre-step
# journal entry is no longer just flagged -- time to page is recomputed in that entry's own
# clock frame: boot_epoch_pre_ms = __REALTIME_TIMESTAMP - __MONOTONIC_TIMESTAMP (us -> ms) of
# the last `journalctl -b -o export` entry before the step, ttp = beacon epoch - that boot
# epoch, output tagged frame=pre-step (not SUSPECT -- the frame was recovered). With no step
# after the beacon, the existing computation stands, tagged frame=post-step. SUSPECT is now
# reserved for a step after the beacon with NO pre-step entry to recover from (the existing
# LATE case above: its journalctl -o export stub returns nothing, so this is exactly that
# case -- no frame= tag is asserted for it, since the ruling does not say one accompanies an
# uncorrected SUSPECT).
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

# A journalctl -o export entry at monotonic 18.5s (before the LATE_STEP's 25.123456s) whose
# own realtime/monotonic fields give a DIFFERENT boot epoch than the naive rollover-based one
# above -- so a test that used the naive BOOT either way could not tell pre-step correction
# happened. boot_epoch_pre_ms = (1699999800000000 - 18500000) / 1000 = 1699999781500.0
# ttp_pre = (EPOCH_MS - boot_epoch_pre_ms) / 1000 = (1699999820500 - 1699999781500) / 1000 = 39.00
# The blank line at the end is not incidental -- journalctl -o export terminates EVERY entry,
# including the last, with one; a reader that only commits an entry on the blank line after
# it would otherwise silently drop this one.
PRE_STEP_EXPORT='__REALTIME_TIMESTAMP=1699999800000000
__MONOTONIC_TIMESTAMP=18500000
MESSAGE=boot message before the step

'
WANT_TTP_PRE='39.00'

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
# Three call shapes: "-u kiosk -o cat" (find the TITLE line, measure-page.sh only),
# "-o export" (the pre-step frame's __REALTIME_TIMESTAMP/__MONOTONIC_TIMESTAMP, #185
# 2026-10-04), and "-o short-monotonic" (find clock-step lines) -- checked in that order
# since "-o export" and "-o short-monotonic" both lack "-u kiosk".
case "$*" in
    *"-u kiosk"*) printf 'TITLE T %s\n' "$TTP_EPOCH_MS" ;;
    *"-o export"*) [ -n "${TTP_EXPORT_DUMP:-}" ] && printf '%s' "$TTP_EXPORT_DUMP" ;;
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
# surf prefixes every window title -- the real board shows
# `WM_NAME(STRING) = "@cgDISMfxT:- | T 1791152777902"`, never a bare "T <epoch_ms>". The
# equality cases below exercise that realistic, prefixed form; TTP_WM_NAME, when set,
# overrides it entirely for the dedicated title-parsing cases further down.
if [ -n "${TTP_WM_NAME:-}" ]; then
    printf 'WM_NAME(STRING) = "%s"\n' "$TTP_WM_NAME"
else
    printf 'WM_NAME(STRING) = "@cgDISMfxT:- | T %s"\n' "$TTP_EPOCH_MS"
fi
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
        TTP_STEP_LINE="${TTP_STEP_LINE:-}" TTP_STATE="$STATE" TTP_WM_NAME="${TTP_WM_NAME:-}" \
        TTP_EXPORT_DUMP="${TTP_EXPORT_DUMP:-}" \
        sh "$script" 115
}

field() {
    # field <output> <label> -- the value after "label:" or "label_s:", trimmed.
    printf '%s\n' "$1" | sed -n "s/^$2:[[:space:]]*//p"
}

check_case() {
    local name=$1 want_suspect=$2 want_ttp=$3 want_frame=${4:-}
    STATE=$(mktemp -d); mkdir -p "$STATE"
    local out_measure out_x

    rm -f "$STATE/date_calls"
    out_measure=$(run "$MEASURE_PAGE")
    rm -f "$STATE/date_calls"
    out_x=$(run "$TTP_X")
    rm -rf "$STATE"

    local boot_m boot_x ttp_m ttp_x susp_m susp_x frame_m frame_x
    boot_m=$(field "$out_measure" "boot_epoch_ms")
    boot_x=$(field "$out_x" "boot_epoch_ms")
    ttp_m=$(field "$out_measure" "RESULT_time_to_page_s")
    ttp_x=$(field "$out_x" "RESULT_time_to_page_s")
    susp_m=$([[ "$out_measure" == *"SUSPECT:"* ]] && echo yes || echo no)
    susp_x=$([[ "$out_x" == *"SUSPECT:"* ]] && echo yes || echo no)
    frame_m=$([[ "$out_measure" == *"$want_frame"* ]] && echo yes || echo no)
    frame_x=$([[ "$out_x" == *"$want_frame"* ]] && echo yes || echo no)

    local ok=1
    # The pre-step-corrected boot epoch legitimately differs from WANT_BOOT (the naive
    # rollover-based one); only check boot_epoch_ms equality when no correction is expected.
    if [ -z "$want_frame" ] || [ "$want_frame" != "frame=pre-step" ]; then
        if [ "$boot_m" != "$WANT_BOOT" ] || [ "$boot_x" != "$WANT_BOOT" ]; then ok=0; fi
    elif [ "$boot_m" != "$boot_x" ]; then
        ok=0  # still must agree with each other, even though neither equals WANT_BOOT
    fi
    if [ "$ttp_m" != "$want_ttp" ] || [ "$ttp_x" != "$want_ttp" ]; then ok=0; fi
    if [ "$susp_m" != "$want_suspect" ] || [ "$susp_x" != "$want_suspect" ]; then ok=0; fi
    if [ -n "$want_frame" ] && { [ "$frame_m" = no ] || [ "$frame_x" = no ]; }; then ok=0; fi

    if [ "$ok" -eq 1 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name" >&2
        echo "      boot_epoch_ms   measure-page=$boot_m  time-to-page-x=$boot_x" >&2
        echo "      time_to_page_s  want=$want_ttp   measure-page=$ttp_m  time-to-page-x=$ttp_x" >&2
        echo "      SUSPECT         want=$want_suspect  measure-page=$susp_m  time-to-page-x=$susp_x" >&2
        [ -n "$want_frame" ] && echo "      frame '$want_frame' present  measure-page=$frame_m  time-to-page-x=$frame_x" >&2
    fi
}

# --- time-to-page-x.sh's own title-prefix parsing, X-only -------------------------------
# #185 ruling 2026-10-04 (urgent, blocks S1): surf prefixes every window title; the real
# board's xprop shows `WM_NAME(STRING) = "@cgDISMfxT:- | T 1791152777902"`, and
# time-to-page-x.sh's `case "$t" in 'T '[0-9]*)` is anchored at the START of $t, so a
# prefixed title never matches and every baseline boot times out. These two cases check the
# fix behaviourally against the real script, not its mechanism.
check_x_title_parses() {
    local name=$1 wm_name=$2 want_title=$3
    STATE=$(mktemp -d); rm -f "$STATE/date_calls"
    local out
    TTP_WM_NAME=$wm_name out=$(run "$TTP_X")
    rm -rf "$STATE"
    local got
    got=$(field "$out" "title")
    if [ "$got" = "$want_title" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name: want title='$want_title', got '$got'" >&2
        printf '%s\n' "$out" | sed 's/^/      /' >&2
    fi
}

check_x_title_rejects() {
    local name=$1 wm_name=$2
    STATE=$(mktemp -d); rm -f "$STATE/date_calls"
    local out rc
    TTP_WM_NAME=$wm_name out=$(run "$TTP_X"); rc=$?
    rm -rf "$STATE"
    if [ "$rc" -eq 1 ] && [[ "$out" == *"TIMEOUT"* ]]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name: want TIMEOUT (rc=1), got rc=$rc" >&2
        printf '%s\n' "$out" | sed 's/^/      /' >&2
    fi
}

STUBBIN=$(mktemp -d)
make_stub_bin "$STUBBIN"
trap 'rm -rf "$STUBBIN"' EXIT

TTP_EXPORT_DUMP=''
TTP_STEP_LINE="$LATE_STEP"  check_case "a step after the beacon, no pre-step entry -> SUSPECT in both" \
    yes "$WANT_TTP"
TTP_STEP_LINE="$EARLY_STEP" check_case "a step before the beacon -> SUSPECT in neither, frame=post-step" \
    no "$WANT_TTP" "frame=post-step"

TTP_EXPORT_DUMP="$PRE_STEP_EXPORT"
TTP_STEP_LINE="$LATE_STEP"  check_case "a step after the beacon WITH a pre-step entry -> corrected ttp, frame=pre-step, not SUSPECT" \
    no "$WANT_TTP_PRE" "frame=pre-step"
TTP_EXPORT_DUMP=''

TTP_STEP_LINE=''
check_x_title_parses "surf-prefixed xprop title (the board's own example) parses" \
    '@cgDISMfxT:- | T 1791152777902' 'T 1791152777902'
check_x_title_rejects "a title ending in stray (non-digit) characters after T <n> is rejected" \
    '@x | T 12a'

echo "time-to-page-equality: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
