#!/bin/bash
# Pre-run proofs for #176: config facts bitbake itself must confirm before the
# cold build launches. Runs three bitbake calls in one container shell and
# checks their output; exits nonzero if (a), (b) or (c) fails.
#
# Usage: proofs.sh
set -euo pipefail
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$REPO"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$HERE/write-overlay.sh"
KCONFIG=kiosk-zero-w.yaml; OVERLAY=build/coldbuild/zz-coldbuild.yaml
PROOFS_DIR="$HERE/proofs"; mkdir -p "$PROOFS_DIR"
RAW=build/coldbuild/proofs-raw.txt
set +e
tools/kas-run.sh shell "$KCONFIG:$OVERLAY" -c '
    set -e
    echo "=== bitbake -e webkitgtk3 ==="; bitbake -e webkitgtk3
    echo "=== bitbake -e (global) ==="; bitbake -e
    echo "=== bitbake -g core-image-base ==="; bitbake -g core-image-base >/dev/null
    echo "=== pn-buildlist ==="; cat pn-buildlist
' > "$RAW" 2>&1
kas_rc=$?
set -e
if [ "$kas_rc" -ne 0 ]; then
    echo "proofs.sh: tools/kas-run.sh shell exited $kas_rc -- see $RAW" | tee "$PROOFS_DIR/FAIL.txt" >&2; exit 1
fi
block() { awk -v s="$1" -v e="$2" '$0==s{f=1;next} $0==e{f=0} f' "$RAW"; }
webkit_block=$(block "=== bitbake -e webkitgtk3 ===" "=== bitbake -e (global) ===")
global_block=$(block "=== bitbake -e (global) ===" "=== bitbake -g core-image-base ===")
buildlist_block=$(block "=== pn-buildlist ===" "@@@no-such-marker@@@")
fail=0
# (a) PARALLEL_MAKE:pn-webkitgtk3 == -j6; DEBUG_FLAGS has no -g/-g1 token and
# at least one *prefix-map* token.
parallel_line=$(printf '%s\n' "$webkit_block" | grep -m1 '^PARALLEL_MAKE=' || true)
debug_line=$(printf '%s\n' "$webkit_block" | grep -m1 '^DEBUG_FLAGS=' || true)
{
    echo "PARALLEL_MAKE:pn-webkitgtk3 : $parallel_line"
    echo "DEBUG_FLAGS:pn-webkitgtk3   : $debug_line"
} > "$PROOFS_DIR/a-webkitgtk3-env.txt"
case "$parallel_line" in
    *'"-j6"'*) ;;
    *) echo "FAIL (a): PARALLEL_MAKE:pn-webkitgtk3 is not -j6" >> "$PROOFS_DIR/a-webkitgtk3-env.txt"; fail=1 ;;
esac
if printf '%s\n' "$debug_line" | grep -qw -e -g -e -g1; then
    echo "FAIL (a): DEBUG_FLAGS still carries -g or -g1" >> "$PROOFS_DIR/a-webkitgtk3-env.txt"; fail=1
fi
printf '%s\n' "$debug_line" | grep -q 'prefix-map' \
    || { echo "FAIL (a): DEBUG_FLAGS carries no prefix-map token" >> "$PROOFS_DIR/a-webkitgtk3-env.txt"; fail=1; }
# (b) none of the six removed recipes is in pn-buildlist. A short buildlist_block
# (empty capture, wrong cwd, awk markers not matching) would make the comm check
# below pass vacuously, so the line count is asserted and recorded first.
removed="adwaita-icon-theme librsvg librsvg-native rust-native rust-llvm-native cargo-native"
buildlist_n=$(printf '%s\n' "$buildlist_block" | grep -c . || true)
echo "pn-buildlist line count: $buildlist_n" > "$PROOFS_DIR/b-pn-buildlist.txt"
if [ "$buildlist_n" -lt 50 ]; then
    echo "FAIL (b): pn-buildlist capture has only $buildlist_n lines -- the capture itself is suspect" \
        >> "$PROOFS_DIR/b-pn-buildlist.txt"
    fail=1
else
    found=$(comm -12 <(tr ' ' '\n' <<< "$removed" | sort) <(printf '%s\n' "$buildlist_block" | sort) || true)
    echo "removed recipes still in pn-buildlist: ${found:-none}" >> "$PROOFS_DIR/b-pn-buildlist.txt"
    if [ -n "$found" ]; then
        echo "FAIL (b): removed recipe(s) present: $found" >> "$PROOFS_DIR/b-pn-buildlist.txt"; fail=1
    fi
fi
# (c) BB_HASHEXCLUDE_COMMON contains PARALLEL_MAKE.
hashexclude_line=$(printf '%s\n' "$global_block" | grep -m1 '^BB_HASHEXCLUDE_COMMON=' || true)
echo "BB_HASHEXCLUDE_COMMON: $hashexclude_line" > "$PROOFS_DIR/c-hashexclude.txt"
printf '%s\n' "$hashexclude_line" | grep -qw PARALLEL_MAKE \
    || { echo "FAIL (c): PARALLEL_MAKE not in BB_HASHEXCLUDE_COMMON" >> "$PROOFS_DIR/c-hashexclude.txt"; fail=1; }
if [ "$fail" -ne 0 ]; then
    echo "proofs.sh: one or more checks failed -- see $PROOFS_DIR/{a,b,c}-*.txt" >&2
    exit 1
fi
echo "proofs.sh: (a), (b) and (c) all pass -- see $PROOFS_DIR/{a,b,c}-*.txt"
