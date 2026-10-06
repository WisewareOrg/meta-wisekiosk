#!/usr/bin/env bash
# Self-test for kiosk-screenshot.sh's image-tool dependency, without a reachable kiosk --
# mirrors kiosk-launch-test.sh's "run the SHIPPED script for real with stubs on PATH".
#
#   tools/kiosk-screenshot-test.sh
#
# kiosk-screenshot.sh checks `command -v magick` up front, but reads the capture back
# with a bare `identify` call. On a host carrying only IM7's unified `magick` binary --
# no legacy `convert`/`identify` shims -- that check passes and the later call then fails
# with "identify: command not found". Because the script does not check that command
# substitution's exit status, MIN/MAX/MEAN all come back empty, "$MIN" = "$MAX" is true
# on two empty strings, and the result is a wrong, confident "BLANK: every pixel
# identical" instead of a tool-missing error.
#
# ssh and scp are stubbed on PATH so the capture and fetch succeed without a device: the
# stub ssh prints a fixed clock line, the stub scp copies a real, non-uniform, 2x2 PPM
# fixture to whatever local path it is given. PATH is then restricted to the stub dir plus
# /usr/bin and /bin (which on this host carry neither magick nor identify, confirmed
# below), so magick's presence or absence is controlled precisely rather than inherited
# from whatever happens to be installed. magick itself, when present, is a symlink to the
# real binary: this exercises genuine image conversion and statistics, not a faked reading.
set -uo pipefail

HERE=$(dirname "$0")
TOOL="$HERE/kiosk-screenshot.sh"
pass=0
fail=0

MAGICK=$(command -v magick) || { echo "SKIPPED: no magick on this host -- cannot test the identify step" >&2; echo "kiosk-screenshot: pass=0 fail=0"; exit 0; }
# The restricted PATH below is "<stub dir>:/usr/bin:/bin" -- only those two
# directories can leak a real identify past the stub, so only they are
# checked. A legacy shim anywhere else on the ambient PATH (this host's own
# imagemagick, wherever it lives) does not compromise the isolation.
if [ -e /usr/bin/identify ] || [ -e /bin/identify ]; then
    echo "SKIPPED: a legacy identify shim exists in /usr/bin or /bin on this host -- cannot isolate magick-only PATH" >&2
    echo "kiosk-screenshot: pass=0 fail=0"
    exit 0
fi

STUB=$(mktemp -d)
trap 'rm -rf "$STUB"' EXIT

# A real, non-uniform PPM: two corners black and white, so BLANK (min==max)
# is false only when the identify step actually ran.
FIXTURE="$STUB/capture.ppm"
printf 'P6\n2 2\n255\n' > "$FIXTURE"
printf '\x40\x40\x40\x80\x80\x80\x00\x00\x00\xff\xff\xff' >> "$FIXTURE"

cat > "$STUB/ssh" << 'EOF'
#!/usr/bin/env bash
echo "12:34:56"
EOF
cat > "$STUB/scp" << EOF
#!/usr/bin/env bash
cp "$FIXTURE" "\${@: -1}"
EOF
chmod +x "$STUB/ssh" "$STUB/scp"

check() {
    local name=$1 got=$2 want_present=$3 want_absent=${4:-}
    local ok=1
    if [ -n "$want_present" ] && [[ "$got" != *"$want_present"* ]]; then ok=0; fi
    if [ -n "$want_absent" ] && [[ "$got" == *"$want_absent"* ]]; then ok=0; fi
    if [ "$ok" -eq 1 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name" >&2
        echo "      want present: '$want_present'  want absent: '$want_absent'" >&2
        echo "      got: $got" >&2
    fi
}

# Case 1: only magick on PATH -- the identify step must still work.
magick_dir="$STUB/magick-only"
mkdir -p "$magick_dir"
ln -s "$STUB/ssh" "$magick_dir/ssh"
ln -s "$STUB/scp" "$magick_dir/scp"
ln -s "$MAGICK" "$magick_dir/magick"
OUT1="$STUB/out1.png"
GOT1=$(env -i PATH="$magick_dir:/usr/bin:/bin" HOME="$STUB" \
    bash "$TOOL" root@kiosk-screenshot-test.invalid "$OUT1" 2>&1)
RC1=$?
check "magick-only PATH: identify step succeeds (rc 0)" "$RC1" "0"
check "magick-only PATH: reports not blank, not a false BLANK verdict" "$GOT1" \
    "not blank." "BLANK: every pixel identical"

# Case 2: neither magick nor identify on PATH -- the existing up-front check must
# still refuse with a clear message, unaffected by the identify-step fix.
neither_dir="$STUB/neither"
mkdir -p "$neither_dir"
ln -s "$STUB/ssh" "$neither_dir/ssh"
ln -s "$STUB/scp" "$neither_dir/scp"
OUT2="$STUB/out2.png"
GOT2=$(env -i PATH="$neither_dir:/usr/bin:/bin" HOME="$STUB" \
    bash "$TOOL" root@kiosk-screenshot-test.invalid "$OUT2" 2>&1)
RC2=$?
check "neither tool on PATH: refuses (rc 1)" "$RC2" "1"
check "neither tool on PATH: clear message naming magick" "$GOT2" \
    "imagemagick (magick) is required on this host"

# Case 3: magick is present and the conversion step succeeds, but the stats
# step itself fails (exits non-zero, prints nothing) -- the class N6 belongs
# to, not just the one instance: ANY way the stats step can fail must be
# surfaced as an error, never silently misread as BLANK on the two empty
# strings its unchecked exit status leaves behind. The stub magick tells the
# two steps apart by the presence of -format (used only by whatever form the
# stats read takes, "magick identify -format ..." or "magick <file> -format
# ... info:"), not by a specific subcommand spelling, so it exercises the fix
# regardless of which form it takes.
stats_fail_dir="$STUB/stats-fail"
mkdir -p "$stats_fail_dir"
ln -s "$STUB/ssh" "$stats_fail_dir/ssh"
ln -s "$STUB/scp" "$stats_fail_dir/scp"
cat > "$stats_fail_dir/magick" << 'EOF'
#!/usr/bin/env bash
for a in "$@"; do
    [ "$a" = "-format" ] && exit 1
done
: > "${@: -1}"
EOF
chmod +x "$stats_fail_dir/magick"
OUT3="$STUB/out3.png"
GOT3=$(env -i PATH="$stats_fail_dir:/usr/bin:/bin" HOME="$STUB" \
    bash "$TOOL" root@kiosk-screenshot-test.invalid "$OUT3" 2>&1)
RC3=$?
if [ "$RC3" -ne 0 ]; then
    pass=$((pass + 1))
else
    fail=$((fail + 1))
    echo "FAIL  stats step failing must not exit 0" >&2
    echo "      got rc=$RC3" >&2
fi
check "stats step failing: never read as BLANK" "$GOT3" "" "BLANK"
check "stats step failing: a message names the stats failure" "$GOT3" \
    "could not read capture statistics"

echo "kiosk-screenshot: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
