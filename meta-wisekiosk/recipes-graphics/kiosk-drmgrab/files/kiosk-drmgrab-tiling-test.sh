#!/usr/bin/env bash
# Host test for kiosk-scanout.h's t_offset(), the VC4 T-tiled address map, and
# kiosk-framepace.c's region offsets and hash.
#
#   meta-wisekiosk/recipes-graphics/kiosk-drmgrab/files/kiosk-drmgrab-tiling-test.sh
#
# Extracts the SHIPPED t_offset() verbatim from kiosk-scanout.h, which both
# tools include -- never a copy, never modified -- and kiosk-framepace.c's
# region block (between its "region: begin" and "region: end" markers), and
# compiles them with the host compiler alongside kiosk-drmgrab-tiling-test.c's
# independent references and test cases (see that file's header for what is
# checked and the mesa citations it is checked against). Neither test file is
# part of the recipe's SRC_URI, so nothing here reaches the image.
set -euo pipefail
cd "$(dirname "$0")"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

awk '/^static size_t t_offset\(/{p=1} p{print} p&&/^}$/{exit}' kiosk-scanout.h \
	> "$tmp/shipped_t_offset.inc"
if [ ! -s "$tmp/shipped_t_offset.inc" ]; then
	echo "kiosk-drmgrab-tiling-test.sh: t_offset() not found in kiosk-scanout.h" >&2
	exit 1
fi
awk '/^\/\* region: end \*\/$/{exit} p{print} /^\/\* region: begin \*\/$/{p=1}' kiosk-framepace.c \
	> "$tmp/shipped_region.inc"
if [ ! -s "$tmp/shipped_region.inc" ]; then
	echo "kiosk-drmgrab-tiling-test.sh: region block not found in kiosk-framepace.c" >&2
	exit 1
fi

"${CC:-cc}" -O2 -Wall -Wextra -I"$tmp" -o "$tmp/test" kiosk-drmgrab-tiling-test.c
"$tmp/test"
