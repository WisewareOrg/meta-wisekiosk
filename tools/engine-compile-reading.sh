#!/usr/bin/env bash
# Compiles wpewebkit once against the shared compile cache and writes what the cache did to
# build/engine-compile-reading.txt. Read by tests/compile_cache.
set -euo pipefail
ARM=option
cd "$(dirname "$0")/.."
reading=build/engine-compile-reading.txt
rm -f "$reading"

block=$(cat <<'BLOCK'
set -euo pipefail
reading=engine-compile-reading.txt
bitbake -c clean wpewebkit
bitbake -c prepare_recipe_sysroot wpewebkit
bitbake -e wpewebkit > bitbake-env.txt
CCACHE_DIR=$(sed -En 's/^(export )?CCACHE_DIR="(.*)"$/\2/p;T;q' bitbake-env.txt)
case "$CCACHE_DIR" in
    */ccache/arm1176jzfshf-vfp-poky-linux-gnueabi/wpewebkit) ;;
    *) echo "CCACHE_DIR is '$CCACHE_DIR': the seed is missing, no compile started" >&2; exit 1 ;;
esac
[ -d "$CCACHE_DIR" ] || { echo "$CCACHE_DIR does not exist: the seed is missing, no compile started" >&2; exit 1; }
export CCACHE_DIR
workdir=$(sed -En 's/^WORKDIR="(.*)"$/\1/p;T;q' bitbake-env.txt)
C=$workdir/recipe-sysroot-native/usr/bin/ccache
[ -x "$C" ] || { echo "no ccache at $C" >&2; exit 1; }
size_kib=$(du -sk "$CCACHE_DIR" | cut -f 1)
[ "$size_kib" -gt 102400 ] || { echo "the seed holds $size_kib KiB, under 100 MB: no compile started" >&2; exit 1; }
"$C" -s
"$C" -z

cstat() { "$C" --print-stats | awk -F'\t' -v k="$1" '$1 == k { v = $2 } END { print v + 0 }'; }
cmake_cache=$workdir/build/CMakeCache.txt
write_reading() { # state do_compile_s: the whole file, moved into place
    {
        echo "arm=$ARM"
        echo "state=$1"
        echo "do_compile_s=$2"
        if [ -e "$cmake_cache" ]; then
            echo "use_woff2=$(sed -n 's/^USE_WOFF2:[A-Z]*=//p' "$cmake_cache")"
            echo "build_type=$(sed -n 's/^CMAKE_BUILD_TYPE:[A-Z]*=//p' "$cmake_cache")"
        fi
        "$C" --print-stats | tr '\t' '='
    } > "$reading.tmp"
    mv "$reading.tmp" "$reading"
}
bitbake -c compile wpewebkit &
bb=$!
state=
checked=0
tick=0
while kill -0 "$bb" 2>/dev/null; do
    sleep 5
    tick=$((tick + 1))
    [ $((tick % 120)) -ne 0 ] || { date; "$C" -s; }
    [ $((tick % 6)) -eq 0 ] || continue
    write_reading stopped ""
    [ "$checked" -eq 0 ] || continue
    hits=$(( $(cstat direct_cache_hit) + $(cstat preprocessed_cache_hit) ))
    miss=$(cstat cache_miss)
    calls=$((hits + miss))
    [ "$calls" -ge 500 ] || continue
    checked=1
    if { [ "$ARM" = control ] && [ $((hits * 100)) -lt $((calls * 95)) ]; } ||
        { [ "$ARM" = option ] && [ $((miss * 100)) -gt $((calls * 90)) ]; }; then
        state=stopped-early
        kill "$bb" 2>/dev/null || true
    fi
done
rc=0
wait "$bb" || rc=$?
if [ -z "$state" ]; then
    [ "$rc" -eq 0 ] || { echo "bitbake -c compile wpewebkit exited $rc" >&2; exit 1; }
    state=ended
fi
do_compile_s=
if [ "$state" = ended ]; then
    stats=$(ls -t tmp-raspberrypi0-wifi/buildstats/*/wpewebkit-*/do_compile 2>/dev/null | sed -n 1p || true)
    [ -z "$stats" ] || do_compile_s=$(sed -n 's/^Elapsed time: \([0-9.]*\) seconds.*/\1/p' "$stats")
fi
write_reading "$state" "$do_compile_s"
cat "$reading"
BLOCK
)

wrapper="timeout -k 10 2700 bash -c $(printf '%q' "ARM=$ARM; $block"); rc=\$?
if [ \$rc -eq 124 ] || [ \$rc -eq 137 ]; then echo 'block stopped by its cap'; exit 0; fi
exit \$rc"
tools/kas-run.sh shell kiosk-zero-w.yaml -c "$wrapper"
if [ ! -e "$reading" ]; then
    printf 'arm=%s\nstate=stopped\n' "$ARM" > "$reading"
    cat "$reading"
fi
