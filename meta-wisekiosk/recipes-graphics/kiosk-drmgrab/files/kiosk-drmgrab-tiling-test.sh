#!/usr/bin/env bash
# Host test for kiosk-drmgrab.c's t_offset(): the VC4 T-tiled address map.
#
#   meta-wisekiosk/recipes-graphics/kiosk-drmgrab/files/kiosk-drmgrab-tiling-test.sh
#
# Extracts the SHIPPED t_offset() verbatim from kiosk-drmgrab.c -- never a copy,
# never modified -- and compiles it with the host compiler alongside
# kiosk-drmgrab-tiling-test.c's independent reference and test cases (see that
# file's header for what is checked and the mesa citations it is checked
# against). Neither file is part of the recipe's SRC_URI, so nothing here
# reaches the image.
set -euo pipefail
cd "$(dirname "$0")"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

awk '/^static size_t t_offset\(/{p=1} p{print} p&&/^}$/{exit}' kiosk-drmgrab.c \
	> "$tmp/shipped_t_offset.inc"
if [ ! -s "$tmp/shipped_t_offset.inc" ]; then
	echo "kiosk-drmgrab-tiling-test.sh: t_offset() not found in kiosk-drmgrab.c" >&2
	exit 1
fi

"${CC:-cc}" -O2 -Wall -Wextra -I"$tmp" -o "$tmp/test" kiosk-drmgrab-tiling-test.c
"$tmp/test"
