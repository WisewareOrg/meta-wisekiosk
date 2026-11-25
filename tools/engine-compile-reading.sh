#!/usr/bin/env bash
# Compiles wpewebkit once against the shared compile cache and writes what the cache did to
# build/engine-compile-reading.txt. Read by tests/compile_cache.
set -euo pipefail
ARM=option
cd "$(dirname "$0")/.."
rm -f build/engine-compile-reading.txt

block=$(cat <<'BLOCK'
set -euo pipefail
reading=engine-compile-reading.txt
bitbake -c clean wpewebkit
bitbake -c prepare_recipe_sysroot wpewebkit
env_dump=$(bitbake -e wpewebkit)
CCACHE_DIR=$(printf '%s\n' "$env_dump" | sed -En 's/^(export )?CCACHE_DIR="(.*)"$/\2/p;T;q')
case "$CCACHE_DIR" in
    */ccache/arm1176jzfshf-vfp-poky-linux-gnueabi/wpewebkit) ;;
    *) echo "CCACHE_DIR is '$CCACHE_DIR': the seed is missing, no compile started" >&2; exit 1 ;;
esac
[ -d "$CCACHE_DIR" ] || { echo "$CCACHE_DIR does not exist: the seed is missing, no compile started" >&2; exit 1; }
export CCACHE_DIR
workdir=$(printf '%s\n' "$env_dump" | sed -En 's/^WORKDIR="(.*)"$/\1/p;T;q')
C=$workdir/recipe-sysroot-native/usr/bin/ccache
[ -x "$C" ] || { echo "no ccache at $C" >&2; exit 1; }
"$C" -s
size_kib=$("$C" --print-stats | awk -F'\t' '$1 == "cache_size_kibibyte" { print $2 }')
[ "${size_kib:-0}" -gt 102400 ] || { echo "the seed holds ${size_kib:-0} KiB, under 100 MB: no compile started" >&2; exit 1; }
"$C" -z
( while true; do sleep 600; date; "$C" -s; done ) &
loop=$!
rc=0
timeout -k 10 2400 bitbake -c compile wpewebkit || rc=$?
kill "$loop" 2>/dev/null || true
case "$rc" in
    0) state=ended ;;
    124|137) state=stopped ;;
    *) echo "bitbake -c compile wpewebkit exited $rc" >&2; exit 1 ;;
esac
do_compile_s=
if [ "$state" = ended ]; then
    stats=$(ls -t tmp-raspberrypi0-wifi/buildstats/*/wpewebkit-*/do_compile 2>/dev/null | sed -n 1p || true)
    [ -z "$stats" ] || do_compile_s=$(sed -n 's/^Elapsed time: \([0-9.]*\) seconds.*/\1/p' "$stats")
fi
cmake_cache=$workdir/build/CMakeCache.txt
{
    echo "arm=$ARM"
    echo "state=$state"
    echo "do_compile_s=$do_compile_s"
    echo "use_woff2=$(sed -n 's/^USE_WOFF2:[A-Z]*=//p' "$cmake_cache")"
    echo "build_type=$(sed -n 's/^CMAKE_BUILD_TYPE:[A-Z]*=//p' "$cmake_cache")"
    "$C" --print-stats | tr '\t' '='
} > "$reading"
cat "$reading"
BLOCK
)

tools/kas-run.sh shell kiosk-zero-w.yaml -c "ARM=$ARM; $block"
