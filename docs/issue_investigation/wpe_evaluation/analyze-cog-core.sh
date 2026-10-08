#!/bin/bash
# analyze-cog-core.sh <capture-dir> <build-tmp-dir> -- read a cog core collected by
# capture-cog-core.sh with gdb: `bt full` and `thread apply all bt`, into
# <capture-dir>/backtrace.txt.
#
# <build-tmp-dir> is the bitbake TMPDIR (e.g. build/tmp-raspberrypi0-wifi) that built the image
# the board ran. The sysroot is that image's rootfs with the cog, wpewebkit, libwpe,
# wpebackend-fdo and glib-2.0 -dbg packages overlaid, so each library's .debug/ sits beside it.
# Refuses, exit 2, unless the capture's /etc/buildinfo line and cog identity (build-id or md5)
# equal the rootfs's.
# gdb is nixpkgs' multi-target build, run through `nix shell nixpkgs#gdb`.
set -u
CAP=${1:?capture-dir}; TMP=${2:?build-tmp-dir}
ROOTFS=$TMP/work/raspberrypi0_wifi-poky-linux-gnueabi/core-image-base/1.0/rootfs
W=$TMP/work/arm1176jzfshf-vfp-poky-linux-gnueabi

CORE=$(find "$CAP" -maxdepth 1 -name 'core.*' -type f | head -n 1)
[ -n "$CORE" ] || { echo "no core.* in $CAP" >&2; exit 2; }
[ -d "$ROOTFS" ] || { echo "no image rootfs at $ROOTFS" >&2; exit 2; }
want=$(grep '^meta-wisekiosk ' "$CAP/buildinfo.txt" 2>/dev/null)
have=$(grep '^meta-wisekiosk ' "$ROOTFS/etc/buildinfo" 2>/dev/null)
if [ -z "$want" ] || [ "$want" != "$have" ]; then
	echo "build mismatch: capture '${want:-none}', rootfs '${have:-none}'" >&2
	exit 2
fi

read -r kind id < "$CAP/cog-id.txt" 2>/dev/null
case "${kind:-}" in
build-id) got=$(readelf -n "$ROOTFS/usr/bin/cog" | sed -n 's/.*Build ID: *//p') ;;
md5) got=$(md5sum < "$ROOTFS/usr/bin/cog" | cut -d' ' -f1) ;;
*) echo "no cog identity in $CAP/cog-id.txt" >&2; exit 2 ;;
esac
[ "$got" = "$id" ] || { echo "cog mismatch: capture $kind $id, rootfs $got" >&2; exit 2; }

SYS=$(mktemp -d)
trap 'rm -rf "$SYS"' EXIT
cp -a "$ROOTFS/." "$SYS/" || { echo "could not copy $ROOTFS" >&2; exit 2; }
for d in cog/*/packages-split/cog-dbg wpewebkit/*/packages-split/wpewebkit-dbg \
	libwpe/*/packages-split/libwpe-dbg wpebackend-fdo/*/packages-split/wpebackend-fdo-dbg \
	glib-2.0/*/packages-split/glib-2.0-dbg; do
	src=$(compgen -G "$W/$d" | head -n 1)
	[ -n "$src" ] || { echo "missing $W/$d" >&2; exit 2; }
	cp -a "$src/." "$SYS/"
done

cat > "$SYS/cmds.gdb" <<EOF
set pagination off
set confirm off
set sysroot $SYS
set solib-search-path $SYS/usr/lib:$SYS/lib:$SYS/usr/lib/cog/modules:$SYS/usr/lib/wpe-webkit-2.0
set debug-file-directory $SYS/usr/lib/debug
file $SYS/usr/bin/cog
core-file $CORE
info sharedlibrary
bt full
thread apply all bt
EOF

{
	echo "# analyze-cog-core.sh core=$(basename "$CORE") $have cog $kind $id"
	nix shell nixpkgs#gdb -c gdb --version | head -n 1
	nix shell nixpkgs#gdb -c gdb -batch -x "$SYS/cmds.gdb" 2>&1
} > "$CAP/backtrace.txt"
echo "wrote $CAP/backtrace.txt"
