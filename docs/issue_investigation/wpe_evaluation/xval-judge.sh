#!/bin/bash
# xval-judge.sh <dir> <static-crop> <clock-crop>
#
# Judges an xval-capture.sh directory. Crops are WxH+X+Y, chosen by looking at the captures.
#   rc 0  pass: all four frames 1280x720, AE = 0 between helper and import on the static crop in
#         both pairs, and helper A vs helper B AE > 0 on the clock crop
#   rc 1  fail: a frame not 1280x720, a static-crop AE != 0, or the clock crop unchanged
#   rc 2  could not judge: a frame missing or unreadable, a crop not wholly inside the frame, a
#         tool failure, or the static crop too flat to expose a de-tile or channel-order bug
#         (< 256 colours, or < 1% of pixels with |R-B| >= 32)
# Full-frame AE per pair is printed, not judged. Needs ImageMagick on this host.
set -u
D=${1:?dir}; S=${2:?static-crop}; C=${3:?clock-crop}

ae() {
	local out rc
	out=$(compare -metric AE "$1" "$2" null: 2>&1); rc=$?
	[ $rc -le 1 ] || { echo "cannot compare $1 $2: $out" >&2; exit 2; }
	echo "${out%% *}"
}

for f in A.ppm A.png B.ppm B.png; do
	dim=$(identify -format '%wx%h' "$D/$f" 2>&1) || { echo "$f unreadable: $dim"; exit 2; }
	echo "$f $dim"
	[ "$dim" = 1280x720 ] || { echo "FAIL: $f is $dim, not 1280x720"; exit 1; }
done

for g in "$S" "$C"; do
	[[ $g =~ ^([0-9]+)x([0-9]+)\+([0-9]+)\+([0-9]+)$ ]] ||
		{ echo "COULD NOT JUDGE: bad crop geometry '$g'"; exit 2; }
	m=("${BASH_REMATCH[@]}")
	if [ "${m[1]}" -eq 0 ] || [ "${m[2]}" -eq 0 ] ||
		[ $((m[1] + m[3])) -gt 1280 ] || [ $((m[2] + m[4])) -gt 720 ]; then
		echo "COULD NOT JUDGE: crop outside frame ($g)"; exit 2
	fi
done

colours=$(identify -format '%k' "$D/A.ppm[$S]" 2>&1) ||
	{ echo "COULD NOT JUDGE: identify failed on the static crop: $colours"; exit 2; }
rb=$(magick "$D/A.ppm[$S]" -fx 'abs(r-b)>=32/255' -format '%[fx:mean]' info: 2>&1) ||
	{ echo "COULD NOT JUDGE: magick failed on the static crop: $rb"; exit 2; }
echo "static crop $S: $colours colours, |R-B|>=32 on fraction $rb"
if [ "$colours" -lt 256 ] || awk -v f="$rb" 'BEGIN { exit !(f < 0.01) }'; then
	echo "COULD NOT JUDGE: crop too flat"; exit 2
fi

rc=0
for p in A B; do
	a=$(ae "$D/$p.ppm" "$D/$p.png") || exit 2
	echo "pair $p full-frame AE $a (recorded, not judged)"
	a=$(ae "$D/$p.ppm[$S]" "$D/$p.png[$S]") || exit 2
	echo "pair $p static-crop AE $a"
	[ "$a" = 0 ] || rc=1
done
c=$(ae "$D/A.ppm[$C]" "$D/B.ppm[$C]") || exit 2
echo "helper A vs B clock-crop AE $c"
[ "$c" = 0 ] && rc=1

[ $rc = 0 ] && echo "PASS" || echo "FAIL"
exit $rc
