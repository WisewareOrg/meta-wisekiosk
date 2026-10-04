#!/bin/bash
# After a cold-build attempt finishes: packs its buildstats, runs the parser,
# and pulls the manifest/local.conf/compile-log facts into this directory,
# named after the buildstats run so repeat attempts never overwrite each other.
#
# Usage: collect.sh [buildstats_run_dir]   (default: the newest one)
set -euo pipefail
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$REPO"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BSDIR=${1:-$(find build/coldbuild -mindepth 3 -maxdepth 3 -type d -path '*/buildstats/*' 2>/dev/null | sort | tail -1 || true)}
if [ -z "$BSDIR" ] || [ ! -d "$BSDIR" ]; then
    echo "collect.sh: no buildstats run dir (pass one, or build/coldbuild/tmp*/buildstats/<run>/)" >&2; exit 1
fi
RUNID=$(basename "${BSDIR%/}")
tar -cJf "$HERE/buildstats-$RUNID.tar.xz" -C "$(dirname "${BSDIR%/}")" "$RUNID"
python3 "$HERE/parse_buildstats.py" "$BSDIR" > "$HERE/parse-report-$RUNID.md"
# No -type filter: bitbake's log.do_compile is a symlink to the timestamped
# log, not a regular file.
COMPILE_LOG=$(find build/coldbuild -path '*/webkitgtk3/*/temp/log.do_compile' 2>/dev/null | head -1 || true)
{
    echo "# webkitgtk3 log.do_compile excerpt ($RUNID) -- source: ${COMPILE_LOG:-not found}"
    [ -n "$COMPILE_LOG" ] && grep -m1 -E '\-c ' "$COMPILE_LOG"
    [ -n "$COMPILE_LOG" ] && grep -m1 -E 'ninja -v -j' "$COMPILE_LOG"
} > "$HERE/webkit-compile-line-$RUNID.txt" || true
# No -type filter: the undated .manifest symlink points at the real, dated one.
MANIFEST=$(find build/coldbuild -path '*/deploy/images/*/core-image-base-*.rootfs.manifest' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2- || true)
[ -n "$MANIFEST" ] && cp "$MANIFEST" "$HERE/manifest-packages-$RUNID.txt"
grep -E '^(TMPDIR|SSTATE_DIR|BUILDHISTORY_DIR|DL_DIR)\b' build/conf/local.conf > "$HERE/local-conf-dirs-$RUNID.txt" || true
echo "collect.sh: wrote evidence for run $RUNID into $HERE"
