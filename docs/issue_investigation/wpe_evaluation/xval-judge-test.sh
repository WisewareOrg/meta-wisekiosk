#!/usr/bin/env bash
# Self-test for xval-judge.sh's verdict, driven against the SHIPPED tool as a subprocess --
# xval-judge.sh has no sourceable pure-logic function the way kiosk-render-check.sh's
# render_verdict does (it is one top-to-bottom script that calls identify/magick/compare on
# real files throughout), so "reach the shipped code, not a copy" means running the real
# script against real, synthetic PPM/PNG frames rather than symbolic probe text.
#
#   tools/xval-judge-test.sh
#
# xval-judge-fixtures.py (test-only, not shipped) builds each case's A.ppm/A.png/B.ppm/B.png:
# a 1280x720 frame with a 100x100 STATIC region (identical between the "two capture
# methods", helper .ppm and import .png, in the healthy case) and an 80x40 CLOCK region
# that differs between frame A and frame B (the clock moved). See its header for exact
# geometry and xval-judge.sh's header for what each exit code means.
#
# BOTH DIRECTIONS: the PASS and grayscale-PASS cases prove the verdict can return 0 at all;
# every FAIL/COULD-NOT-JUDGE case below is a single, named defect seeded into one otherwise-
# healthy fixture, so each failure mode is pinned by an input the others do not touch.
#
# Needs ImageMagick (identify/magick/compare) on this host, same as the tool under test.
set -uo pipefail

HERE=$(dirname "$0")
TOOL="$HERE/xval-judge.sh"
FIXTURES="$HERE/xval-judge-fixtures.py"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

pass=0
fail=0

STATIC_CROP=100x100+50+50
CLOCK_CROP=80x40+600+600

# check <name> <want-rc> <mode> [static-crop] [clock-crop] [must-contain]
check() {
    local name=$1 want=$2 mode=$3 scrop=${4:-$STATIC_CROP} ccrop=${5:-$CLOCK_CROP} \
          must_contain=${6:-} dir out got
    dir="$WORK/$mode-$$-$RANDOM"
    mkdir -p "$dir"
    python3 "$FIXTURES" "$mode" "$dir" > /dev/null 2>&1
    out=$(bash "$TOOL" "$dir" "$scrop" "$ccrop" 2>&1)
    got=$?
    if [ "$got" -ne "$want" ]; then
        fail=$((fail + 1))
        echo "FAIL  $name: expected rc=$want, got rc=$got" >&2
        echo "      output: $out" >&2
        rm -rf "$dir"
        return
    fi
    if [ -n "$must_contain" ] && [ "${out//$must_contain/}" = "$out" ]; then
        fail=$((fail + 1))
        echo "FAIL  $name: rc=$got as expected, but output did not contain '$must_contain'" >&2
        echo "      output: $out" >&2
        rm -rf "$dir"
        return
    fi
    pass=$((pass + 1))
    rm -rf "$dir"
}

# --- PASS: the legal input the tool must NOT reject -----------------------
check "healthy pair, moving clock -> PASS" 0 pass
check "grayscale frame A, enough grey levels -> PASS (channel order unverifiable, not judged)" \
    0 grayscale_pass "" "" "channel order unverifiable"

# --- FAIL (rc1): a real defect between the two capture methods or over time
check "a channel swap in the static crop -> FAIL" 1 channel_swap
check "a misplaced tile in the static crop -> FAIL" 1 misplaced_tile
check "an unchanged clock crop between A and B -> FAIL" 1 unchanged_clock
check "a frame not 1280x720 -> FAIL" 1 wrong_dims

# --- COULD NOT JUDGE (rc2): the tool must say so, never guess ---------------
check "a static crop too flat to expose a bug (colour) -> rc2" 2 flat_crop "" "" \
    "too flat"
check "a static crop too flat to expose a bug (grayscale, <32 grey levels) -> rc2" \
    2 grayscale_flat "" "" "too flat"
check "a missing frame -> rc2" 2 missing_frame
check "a crop extending past the frame -> rc2" 2 pass "400x300+1200+700" "$CLOCK_CROP" \
    "outside frame"

# A tool on PATH failing must be rc2 AND must name which tool failed -- "cannot judge" with
# no culprit sends a person chasing the wrong command.
check_tool_failure() {
    local dir stub out got
    dir="$WORK/toolfail-$$"
    mkdir -p "$dir"
    python3 "$FIXTURES" pass "$dir" > /dev/null 2>&1
    stub="$WORK/stubpath-$$"
    mkdir -p "$stub"
    cat > "$stub/magick" << 'EOF'
#!/bin/sh
echo "magick: stub failure (simulated PATH tool outage)" >&2
exit 1
EOF
    chmod +x "$stub/magick"
    out=$(PATH="$stub:$PATH" bash "$TOOL" "$dir" "$STATIC_CROP" "$CLOCK_CROP" 2>&1)
    got=$?
    if [ "$got" -ne 2 ]; then
        fail=$((fail + 1))
        echo "FAIL  a stubbed, failing 'magick' on PATH: expected rc=2, got rc=$got" >&2
        echo "      output: $out" >&2
    elif [ "${out//magick/}" = "$out" ]; then
        fail=$((fail + 1))
        echo "FAIL  a stubbed, failing 'magick' on PATH: rc=2 but output never names 'magick'" >&2
        echo "      output: $out" >&2
    else
        pass=$((pass + 1))
    fi
    rm -rf "$dir" "$stub"
}
check_tool_failure

echo "xval-judge: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
