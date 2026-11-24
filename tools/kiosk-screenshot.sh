#!/usr/bin/env bash
# Capture the buffer the kiosk's panel is scanning out, whoever drew it, as a PNG.
#
#   tools/kiosk-screenshot.sh root@<host> [out.png]
#
# Exits 0 with a PNG; 1 with a PNG and BLANK if every pixel is the same; any
# other failure is 1 with the reason on stderr.
#
# The default output goes under local/: a capture is a picture of the site's
# live kiosk page, and local/ is gitignored.
#
# Reading it:
#
#   min=0 max=255 mean~4   healthy page -- black background, sparse light text.
#                          A mean near zero is NORMAL.
#   text console           the browser is not on the panel: not running, still
#                          starting, or an operator is on another console.
#
# It is the primary plane handed to the display hardware, so a mouse pointer is
# not in it, and not what reaches the glass: an unplugged panel reads the same. A frame the page replaces mid-copy can mix two.
#
# A capture cannot tell you the render is LIVE, so the device's clock is taken
# in the same ssh: compare it with the clock the page renders. An existing file
# is never overwritten, so a stale PNG cannot pass for a fresh one.
set -uo pipefail

HOST=${1:?usage: kiosk-screenshot.sh <ssh-target> [out.png]}
OUT=${2:-local/kiosk-$(date +%Y%m%d-%H%M%S).png}

ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)

mkdir -p "$(dirname "$OUT")" || { echo "cannot create $(dirname "$OUT")" >&2; exit 1; }
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture you may be about to read as fresh" >&2; exit 1; }

CAPTURE=$(mktemp) || exit 1
trap 'rm -f "$CAPTURE"' EXIT

ssh "${ssh_opts[@]}" "$HOST" "date '+device clock at capture: %H:%M:%S' >&2; kiosk-drmgrab" > "$CAPTURE" ||
    { echo "capture failed on the device" >&2; exit 1; }

"$(dirname "$0")/scanout-png.py" "$CAPTURE" "$OUT"
