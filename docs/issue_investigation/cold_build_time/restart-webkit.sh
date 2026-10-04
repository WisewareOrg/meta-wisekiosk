#!/bin/bash
# Applies the restart rule once a lower -j has been committed: stops the kas
# container, cleansstates webkitgtk3 against the scratch sstate, rotates the
# previous attempt's logs, and resumes.
#
# Usage: restart-webkit.sh <j>
set -euo pipefail

J=${1:?usage: restart-webkit.sh <j>}

REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$REPO"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

KCONFIG=kiosk-zero-w.yaml
OVERLAY=build/coldbuild/zz-coldbuild.yaml

grep -qF "PARALLEL_MAKE:pn-webkitgtk3 = \"-j${J}\"" "$KCONFIG" \
    || { echo "restart-webkit.sh: $KCONFIG does not commit -j${J} for webkitgtk3 -- commit it first" >&2; exit 1; }

cid=$(docker ps -q --filter "ancestor=ghcr.io/siemens/kas/kas" || true)
if [ -n "$cid" ]; then
    docker stop "$cid" >/dev/null
    while [ -n "$(docker ps -q --filter "id=$cid" || true)" ]; do
        sleep 1
    done
fi

tools/kas-run.sh shell "$KCONFIG:$OVERLAY" -c "bitbake -c cleansstate webkitgtk3"

n=1
while [ -e "build/coldbuild/run-$n.log" ]; do
    n=$((n + 1))
done
for f in run.log watch.log; do
    if [ -e "build/coldbuild/$f" ]; then
        mv "build/coldbuild/$f" "build/coldbuild/${f%.log}-$n.log"
    fi
done
if [ -e build/coldbuild/run.done ]; then
    mv build/coldbuild/run.done "build/coldbuild/run-$n.done"
fi

"$HERE/run-cold-build.sh" --resume
