#!/usr/bin/env bash
# watch.sh -- read-only live view of the current pipeline run.
set -euo pipefail
usage() {
    echo "Usage: tools/pipeline/watch.sh [--help]"
    echo "Read-only live view of the pipeline run, refreshed every 5s. q or Ctrl-C quits."
    echo "Exits 2 if ~/.config/wisekiosk/pipeline.env or PIPELINE_DRIVER is missing."
}
[ "${1:-}" != "--help" ] || { usage; exit 0; }
ENV_FILE="$HOME/.config/wisekiosk/pipeline.env"
[ -f "$ENV_FILE" ] || { echo "watch.sh: $ENV_FILE not found" >&2; exit 2; }
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a
[ -d "${PIPELINE_DRIVER:-}" ] || { echo "watch.sh: PIPELINE_DRIVER directory not found" >&2; exit 2; }
STAGES=(build.log bundle.log preflight.log send.log install.log reboot.log
        testimage.log render.log gpu.log rollback.log rollback-reboot.log
        verdict.txt body.md)
# Driver's phase order and the file each phase writes; verdict.txt/body.md both mean "posted".
PHASE_NAMES=(checkout build delta bundle preflight send install reboot testimage render gpu rollback rollback-reboot posted posted)
PHASE_FILES=(checkout.log build.log delta.txt bundle.log preflight.log send.log install.log reboot.log testimage.log render.log gpu.log rollback.log rollback-reboot.log verdict.txt body.md)
median() { sort -n | awk '{a[NR]=$1} END{if (!NR) exit 1
    if (NR % 2) print a[(NR+1)/2]; else print int((a[NR/2]+a[NR/2+1])/2)}'; }
QUEUE_CACHE="queue empty"; QUEUE_TS=0
while :; do
    NOW=$(date +%s)
    clear
    echo "== timer =="
    systemctl --user is-active wisekiosk-pipeline.timer || true
    systemctl --user is-active wisekiosk-pipeline.service || true
    DISABLED="$PIPELINE_DRIVER/local/pipeline/DISABLED"
    [ -f "$DISABLED" ] && head -n1 "$DISABLED"
    if [ $((NOW - QUEUE_TS)) -ge 30 ]; then
        RAW=$(git -C "$PIPELINE_DRIVER" ls-remote origin \
              'refs/heads/gh-readonly-queue/main/*' 2>/dev/null) || RAW=""
        QUEUE_CACHE=$(awk -F'\t' '{n = split($2, a, "/"); ref = a[n]
            if (ref ~ /^pr-[0-9]+-[0-9a-f]+$/) { split(ref, b, "-")
                printf "PR #%s  merge-group %s  base %s\n", b[2], substr($1,1,7), substr(b[3],1,7) } }' \
            <<<"$RAW")
        [ -n "$QUEUE_CACHE" ] || QUEUE_CACHE="queue empty"
        QUEUE_TS=$NOW
    fi
    echo "== queue =="; printf '%s\n' "$QUEUE_CACHE"
    RUN_DIR=$(for d in "$PIPELINE_DRIVER"/local/pipeline/runs/*/; do [ -d "$d" ] || continue
        stat -c '%Y %n' "$d"; done | sort -n | tail -n1 | awk '{print $NF}')
    echo "== run =="
    ACTIVE=""
    if [ -n "$RUN_DIR" ]; then
        echo "${RUN_DIR%/}"
        PHASE=""; PIDX=-1; PM=-1
        for i in "${!PHASE_FILES[@]}"; do
            pf="$RUN_DIR${PHASE_FILES[$i]}"; [ -f "$pf" ] || continue
            m=$(stat -c '%Y' "$pf") || continue
            [ "$m" -ge "$PM" ] && { PM=$m; PIDX=$i; PHASE=${PHASE_NAMES[$i]}; }
        done
        if [ "$PHASE" = posted ]; then
            echo "PHASE: posted"
        elif [ -n "$PHASE" ]; then
            PREV="$RUN_DIR"; [ "$PIDX" -gt 0 ] && [ -f "$RUN_DIR${PHASE_FILES[$((PIDX-1))]}" ] && PREV="$RUN_DIR${PHASE_FILES[$((PIDX-1))]}"
            ELAPSED=$((NOW - $(stat -c '%Y' "$PREV"))); EMIN=$((ELAPSED / 60)); EXTRA=""
            if [ "$PHASE" = build ]; then
                read -r TN TM < <(grep -o 'Running task [0-9]* of [0-9]*' "$RUN_DIR/build.log" \
                    2>/dev/null | tail -n1 | awk '{print $3, $5}') || true
                [ -n "${TN:-}" ] && [ "$TN" -gt 0 ] \
                    && EXTRA="$TN/$TM tasks, elapsed ${EMIN}m, ETA ~$((ELAPSED * (TM - TN) / TN / 60))m"
            else
                DURS=()
                for d in $(for r in "$PIPELINE_DRIVER"/local/pipeline/runs/*/; do
                        [ -d "$r" ] && [ "$r" != "$RUN_DIR" ] || continue
                        stat -c '%Y %n' "$r"
                    done | sort -rn | awk '{print $NF}'); do
                    [ "${#DURS[@]}" -lt 5 ] || break
                    cf="$d${PHASE_FILES[$PIDX]}"; [ -f "$cf" ] || continue
                    pf2="$d"; [ "$PIDX" -gt 0 ] && [ -f "$d${PHASE_FILES[$((PIDX-1))]}" ] && pf2="$d${PHASE_FILES[$((PIDX-1))]}"
                    cm=$(stat -c '%Y' "$cf") && pm2=$(stat -c '%Y' "$pf2") && DURS+=($((cm - pm2))) || true
                done
                [ "${#DURS[@]}" -gt 0 ] \
                    && EXTRA="elapsed ${EMIN}m / typical $(($(printf '%s\n' "${DURS[@]}" | median) / 60))m"
            fi
            echo "PHASE: $PHASE  ${EXTRA:-elapsed ${EMIN}m}"
        fi
        ACTIVE=$(for f in "${STAGES[@]}"; do [ -f "$RUN_DIR$f" ] || continue
            stat -c '%Y %n' "$RUN_DIR$f"; done | sort -n | tail -n1 | awk '{print $NF}')
        for f in "${STAGES[@]}"; do
            [ -f "$RUN_DIR$f" ] || continue
            read -r s m < <(stat -c '%s %Y' "$RUN_DIR$f") || continue
            mark=" "; [ "$RUN_DIR$f" = "$ACTIVE" ] && mark="*"
            printf '%s %-20s %8d bytes  %6ds ago\n' "$mark" "$f" "$s" "$((NOW - m))"
        done
    else
        echo "no runs yet"
    fi
    if [ -n "$ACTIVE" ]; then
        echo "== tail: $(basename "$ACTIVE") =="
        tail -n 12 "$ACTIVE" | \
            ( cd "$PIPELINE_DRIVER" && ./tools/scrub-identity.py --filter ) || true
    fi
    if [ -n "$RUN_DIR" ] && [ -f "${RUN_DIR}verdict.txt" ]; then
        echo "== verdict =="
        cat "${RUN_DIR}verdict.txt"
    fi
    read -r -t 5 -n 1 key || key=""
    [ "$key" = "q" ] && break
done
