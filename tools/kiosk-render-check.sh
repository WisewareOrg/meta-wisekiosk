#!/usr/bin/env bash
# Is the kiosk still PAINTING, or is it showing an hour-old frame?
#
#   tools/kiosk-render-check.sh root@<host> [WxH+X+Y]
#
# The gap every other instrument leaves open. kiosk-tcp-state.sh sees an
# established socket, kiosk-gpu-check.sh sees a web process holding a vc4 render
# node, kiosk-screenshot.sh sees pixels that are not all the same value -- and a
# browser whose compositor stopped an hour ago satisfies all three. Every one of
# those reads the machinery around the render; none reads the render advancing.
#
# HOW IT DECIDES. Capture the scanout twice a few seconds apart with
# kiosk-drmgrab and compare the bytes. Frames identical -> nothing repainted in
# that window -> FROZEN.
#
# THE ASSUMPTION THIS RESTS ON, stated because it is the whole load-bearing
# claim: identical frames are ambiguous between "correctly static" and "frozen",
# and this tool resolves that ambiguity by ASSUMING the kiosk page always has a
# moving element in the captured region. Today that is the seconds field of the
# clock, which is why the default crop is aimed at it. A page that legitimately
# stops moving -- seconds hidden, animation removed, a screensaver -- makes every
# FROZEN verdict here false. If that ever becomes possible, this tool is wrong
# and needs a different signal, not a wider crop.
#
# WHY A CROP, NOT THE WHOLE SCREEN. kiosk-drmgrab reads the framebuffer through an
# uncached mapping, on the 1 GHz ARM11 core the browser is also rendering on; a
# crop reads and writes a fraction of the frame, so the probe is less load on the
# thing it is measuring.
#
# THE DEFAULT CROP IS LAYOUT-SENSITIVE, AND THAT IS ITS SHARPEST EDGE. The region
# has to contain the moving element in EVERY layout the page can take, not just
# the one someone looked at. An earlier default of 520x140+240+30 was aimed at
# the seconds field using a healthy-board capture -- and when the page raises its
# "kiosk service isn't responding" banner, everything below it shifts down by
# about 95 px, the seconds leave the region, and what is left inside is banner
# text. Static text, so the uniform-region guard below does not fire, and a
# perfectly healthy board reads FROZEN. The region was widened to cover both
# positions after that was caught against the live board.
#
# So: before trusting a changed geometry, crop a real capture to it in every
# layout the page has and LOOK -- the moving element must be visibly inside each
# one. A region that merely has something in it proves nothing; the guards here
# cannot tell static content from a moving element that stopped.
#
# TWO TRAPS, BOTH FOUND THE EXPENSIVE WAY.
#
#   (a) A FAILED CAPTURE LOOKS EXACTLY LIKE A FROZEN ONE. A capture that writes
#       nothing hashes to md5sum of empty input, the constant
#       d41d8cd98f00b204e9800998ecf8427e -- so two failures hash identically and
#       read as "unchanged", forever, on a board that may be perfectly healthy.
#       Three guards, all of them, not any one: the capture's exit status, a
#       minimum byte count on the file it produced, and an explicit match against
#       that constant. Every one of them lands on rc2.
#
#   (b) /dev/fb0 IS A DECOY ON THIS BOARD. It holds the console login buffer,
#       not the kiosk: under fkms the browser's frames go to the CRTC's own
#       framebuffer and never touch fb0. Reading fb0 gives a stable hash from a
#       surface the kiosk does not draw to, which is a FROZEN verdict that is true
#       of the framebuffer and says nothing at all about the browser. Capture is
#       kiosk-drmgrab, which reads the framebuffer bound to the active CRTC, and
#       must stay that way.
#
# THE EXIT CODE, three-valued like kiosk-gpu-check.sh:
#
#   0  advancing -- the two frames differ
#   1  FROZEN -- the two frames are byte-identical and both captures verified good
#   2  could not tell -- capture failed, empty or short output, no capture tool,
#      a uniform capture region, or a misinvocation
#
# rc2 is never a quiet rc1. "I could not photograph the screen" and "the screen
# has not changed in five seconds" send a person to two different places, and on
# a wall-mounted panel one of those places is a ladder.
#
# Read-only on the device: two kiosk-drmgrab captures into tmpfs, hashed and
# removed. It injects no input, forces no redraw, and does not perturb a frozen
# board -- a frozen kiosk stays frozen across a run, which is what makes this
# safe to point at prod.
#
# Without a reachable kiosk, what still runs: argument handling, geometry
# validation, the verdict over canned probe text (tools/kiosk-render-check-test.sh),
# and the SSH failure modes.
set -uo pipefail

# The hash of nothing. Trap (a) in one constant: a capture failing and a capture
# succeeding on an unchanged screen produce the same comparison result unless
# this value is named and rejected.
EMPTY_MD5=d41d8cd98f00b204e9800998ecf8427e

# Below this, a frame did not come back. kiosk-drmgrab writes uncompressed PPM, so
# a real crop is tens of kilobytes; this cannot reject one and catches an empty
# or truncated file.
MIN_BYTES=100

# ---------------------------------------------------------------- the verdict
#
# Everything that can regress is in this one function, and it is a pure
# text -> exit code mapping over the probe: it compares hashes and touches no
# device. That is what lets tools/kiosk-render-check-test.sh exercise the SHIPPED
# logic rather than a copy of it -- the test sources this file with
# KIOSK_RENDER_CHECK_LIB=1 and calls this function directly. Keep it pure.
render_verdict() {
    local probe=$1 frames rc_bad short empty h1 h2 mn mx

    # grep -c throughout, never -q: under `set -o pipefail` a -q exits on the
    # first match, the producer dies of SIGPIPE at 141, and the condition reads
    # FALSE exactly when the pattern matched.

    if [ "$(printf '%s\n' "$probe" | grep -c '^cap=0')" -ne 0 ]; then
        echo "cannot tell: no capture tool on the device, so no frame could be captured." >&2
        echo "kiosk-drmgrab is the capture path (meta-wisekiosk/recipes-graphics/kiosk-drmgrab)." >&2
        return 2
    fi

    # Two frames or it is not a comparison. A probe that lost one -- ssh cut
    # mid-run, the remote shell died between captures -- must not be scored
    # against the board.
    frames=$(printf '%s\n' "$probe" | grep -c '^frame ')
    if [ "$frames" -ne 2 ]; then
        echo "cannot tell: the probe returned $frames frame line(s), not 2. There is" >&2
        echo "nothing to compare; this is a transport or probe failure, not a verdict." >&2
        return 2
    fi

    # Trap (a), guard one: the capture's own exit status.
    rc_bad=$(printf '%s\n' "$probe" | grep -c '^frame [0-9] rc=[^0]')
    if [ "$rc_bad" -ne 0 ]; then
        echo "cannot tell: the capture exited non-zero on at least one frame (see the rc=" >&2
        echo "fields above, and any 'err' lines). A capture that did not happen is not" >&2
        echo "a frozen screen -- two failed captures hash identically and would" >&2
        echo "otherwise read as FROZEN on a healthy board." >&2
        return 2
    fi

    # Trap (a), guard two: the file the capture claimed to write is too small to
    # be a frame. Catches a capture that exits 0 having produced nothing.
    short=$(printf '%s\n' "$probe" | awk -v min="$MIN_BYTES" \
        '/^frame /{for(i=1;i<=NF;i++) if($i ~ /^bytes=/){split($i,a,"="); if(a[2]+0 < min) n++}} END{print n+0}')
    if [ "$short" -ne 0 ]; then
        echo "cannot tell: a captured frame is under $MIN_BYTES bytes -- too small to be a" >&2
        echo "frame. The capture returned success without producing an image." >&2
        return 2
    fi

    # Trap (a), guard three: the hash of empty input, named. Unreachable after
    # the two guards above unless one of them is weakened, which is exactly when
    # it is needed.
    empty=$(printf '%s\n' "$probe" | grep -c "^frame [0-9] .*md5=$EMPTY_MD5")
    if [ "$empty" -ne 0 ]; then
        echo "cannot tell: a frame hashed to md5 of EMPTY INPUT ($EMPTY_MD5)." >&2
        echo "The capture produced no bytes. This is the failure mode that reads as" >&2
        echo "FROZEN if it is not checked for." >&2
        return 2
    fi

    # A uniform capture region is could-not-tell, not frozen. If every pixel in
    # the crop is the same value then the two hashes agree for a reason that has
    # nothing to do with the browser: either the page painted nothing there, or
    # the crop no longer covers the moving element the verdict assumes. Scoring
    # that as FROZEN is how a mis-aimed crop sends someone to a wall-mounted
    # panel that is working. The whole-screen blank test is
    # kiosk-screenshot.sh's, and it stays there.
    mn=$(printf '%s\n' "$probe" | sed -n 's/^blank .*min=\([0-9.]*\).*/\1/p')
    mx=$(printf '%s\n' "$probe" | sed -n 's/^blank .*max=\([0-9.]*\).*/\1/p')
    if [ -n "$mn" ] && [ -n "$mx" ] && [ "$mn" = "$mx" ]; then
        echo "cannot tell: every pixel in the captured region is identical (min=max=$mn)." >&2
        echo "Frame identity carries no information about a uniform region. Either the" >&2
        echo "page never painted there or the crop is aimed at background -- re-aim it," >&2
        echo "and use kiosk-screenshot.sh for the whole-screen blank test." >&2
        return 2
    fi

    h1=$(printf '%s\n' "$probe" | sed -n 's/^frame 1 .*md5=\([0-9a-f]*\).*/\1/p')
    h2=$(printf '%s\n' "$probe" | sed -n 's/^frame 2 .*md5=\([0-9a-f]*\).*/\1/p')
    if [ -z "$h1" ] || [ -z "$h2" ]; then
        echo "cannot tell: a frame line carried no md5 field. The probe and this verdict" >&2
        echo "have gone out of step; nothing was compared." >&2
        return 2
    fi

    if [ "$h1" = "$h2" ]; then
        echo "FROZEN: both frames are byte-identical ($h1) across the interval," >&2
        echo "and both captures verified good. Nothing repainted in the captured region." >&2
        echo "The browser is still running and still connected -- that is the point: every" >&2
        echo "other instrument reports this board healthy." >&2
        return 1
    fi

    echo "advancing: the two frames differ ($h1 / $h2), so the"
    echo "render repainted within the interval."
    return 0
}

# Sourced as a library by the self-test: define the verdict and stop, before any
# argument handling or device access. `return` succeeds only when sourced, so an
# ordinary run falls through to exit.
if [ "${KIOSK_RENDER_CHECK_LIB:-0}" = "1" ]; then
    # shellcheck disable=SC2317  # the `||` arm runs when this file is executed, not sourced
    return 0 2>/dev/null || exit 0
fi

# ------------------------------------------------------------------- the tool

# A misinvocation is "I could not tell", not "the board froze" -- so exit 2,
# never 1. `${1:?}` would leave bash's parameter-error status of 1, which is the
# code a caller reads as a frozen panel, and it fires on set-but-empty too.
if [ "${1:-}" = "" ]; then
    echo "usage: kiosk-render-check.sh <ssh-target> [WxH+X+Y]" >&2
    exit 2
fi
HOST=$1

# Covers the clock's seconds field at 1280x720 in both layouts the page takes:
# banner absent, and banner present with everything below it pushed down ~95 px.
# Margin to the left carries the shift a one-digit hour causes. Verified
# by cropping a capture of each layout to this geometry and looking at it -- see
# the header on why "there is something in the region" is not the test.
CROP=${2:-560x300+220+20}

# Validated here rather than on the device: a malformed geometry makes the
# capture fail, which this tool would correctly report as rc2 "capture failed" and send
# someone looking at the board instead of at their own argument.
# `[[ =~ ]]`, not a pipe into `grep -q`: under pipefail a -q exits on the first
# match, the producer dies of SIGPIPE at 141, and the test reads false exactly
# when the geometry is valid.
if ! [[ $CROP =~ ^[0-9]+x[0-9]+\+[0-9]+\+[0-9]+$ ]]; then
    echo "bad crop geometry '$CROP' -- expected WxH+X+Y, e.g. 520x140+240+30" >&2
    exit 2
fi

HERE=$(dirname "$0")

# One round trip through the shared multiplex master, and the interval is spent
# ON the device. Two ssh invocations would put a key exchange between the frames
# -- on the core the browser renders on -- so the probe would be load on the
# thing it measures, and the interval would be whatever the network felt like.
#
# `sh`, not `bash`: busybox userland, no bash. Nothing here uses `head -20`,
# `date +%N` or `ss`, all of which busybox refuses.
#
# The staged frame goes in /tmp, not /data. kiosk-screenshot.sh uses /data because
# its capture has to survive a reboot racing the scp; this one lives for
# milliseconds and never leaves the device, so tmpfs is the lighter choice --
# no flash write, and nothing persists if the run dies.
#
# $CROP is expanded HERE, on the client, so the device captures the geometry this
# run validated.
# shellcheck disable=SC2029
PROBE=$("$HERE/kiosk-ssh.sh" "$HOST" "CROP='$CROP' sh -s" <<'REMOTE'
if command -v kiosk-drmgrab > /dev/null 2>&1; then
    echo "cap=1"
else
    echo "cap=0"
    exit 0
fi
if command -v identify > /dev/null 2>&1; then echo "cap identify=1"; else echo "cap identify=0"; fi
echo "crop $CROP"

F=/tmp/render-check.$$
# stderr is kept and emitted as evidence, never discarded: kiosk-drmgrab names
# the format, modifier or ioctl that failed, which is the difference between a
# broken probe and a broken kiosk, and 2>/dev/null makes those two identical.
grab() {
    n=$1
    err=$(kiosk-drmgrab "$F.$n.ppm" "$CROP" 2>&1)
    rc=$?
    if [ -f "$F.$n.ppm" ]; then
        b=$(wc -c < "$F.$n.ppm")
        m=$(md5sum < "$F.$n.ppm" | cut -d' ' -f1)
    else
        b=0
        m=none
    fi
    echo "frame $n rc=$rc at=$(date '+%H:%M:%S') bytes=$b md5=$m"
    [ -n "$err" ] && printf 'err %s\n' "$err"
}

grab 1
# Long enough that a one-second clock has ticked several times. Integer seconds:
# busybox sleep.
sleep 3
grab 2

# Secondary, and informational only -- the verdict treats a uniform region as
# could-not-tell, not as a failure of the board. Measured on the SECOND frame,
# the one nearest the verdict. Normalised to 0-255 so the numbers read the same
# as kiosk-screenshot.sh's, whose quantum range is 65535.
if command -v identify > /dev/null 2>&1 && [ -f "$F.2.ppm" ]; then
    identify -format 'blank min=%[fx:minima*255] max=%[fx:maxima*255] mean=%[fx:mean*255]\n' "$F.2.ppm" 2>/dev/null
fi

rm -f "$F.1.ppm" "$F.2.ppm"
REMOTE
)
rc=$?
[ $rc -eq 0 ] || { echo "cannot read $HOST: ssh exited $rc" >&2; exit 2; }

printf '%s\n' "$PROBE" | sed 's/^/  /'

render_verdict "$PROBE"
exit $?
