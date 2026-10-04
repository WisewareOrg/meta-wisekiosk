#!/bin/bash
# run-smoothness.sh <ssh-target> <role> <out>
#
# One S1 smoothness capture: a pre-run screenshot into local/ for the card state, then
# ../gpu_compositing/run-appliance.sh unchanged with p7_min.js, prefix MP, 585 s, xprop -len 20000.
# The screenshot is retried every 10 s until it is not blank; still blank (or failing) after
# 120 s is VOID, exit 3, before anything is deployed. The screenshot's path is appended to <out>.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; OUT=${3:?out}
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
GPU=$HERE/../gpu_compositing
SHOT=$ROOT/local/wpe-pre-$(basename "$OUT" .txt).png

for wait in 0 10 20 30 40 50 60 70 80 90 100 110 120; do
	[ "$wait" -gt 0 ] && { rm -f "$SHOT"; sleep 10; }
	"$ROOT/tools/kiosk-screenshot.sh" "$T" "$SHOT" && break
	[ "$wait" -eq 120 ] && { echo "VOID: pre-run screenshot blank or failing for 120 s -- $SHOT" >&2; exit 3; }
done
"$GPU/run-appliance.sh" "$T" "$ROLE" "$GPU/p7_min.js" MP 585 20000 "$OUT"
rc=$?
echo "# pre-run screenshot local/$(basename "$SHOT")" >> "$OUT"
exit $rc
