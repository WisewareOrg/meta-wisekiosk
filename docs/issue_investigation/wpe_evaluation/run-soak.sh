#!/bin/bash
# run-soak.sh <ssh-target> <role> <out>
#
# The 1 h soak under X: mf-probe.js as surf's user script (cache cleared, kiosk restarted) and
# mf-reader.sh detached on the board. After 3600 s + 60 s it appends the MF| log, kiosk-soak
# --summary over the samples taken since the start and those samples themselves, kiosk NRestarts,
# boot id and /proc/vmstat pswpin/pswpout at both ends, /proc/pressure/memory, and kernel OOM lines
# since the start; then it empties script.js and restarts kiosk.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; OUT=${3:?out}
SECS=3600
HERE=$(dirname "$(readlink -f "$0")")
KSSH=$(git -C "$HERE" rev-parse --show-toplevel)/tools/kiosk-ssh.sh
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture" >&2; exit 2; }

{
echo "# run-soak.sh role=$ROLE secs=$SECS"
echo "# started $(date -u +%FT%TZ)"
echo "# probe sha256 local    $(sha256sum < "$HERE/mf-probe.js" | cut -d' ' -f1)"
} > "$OUT"
"$KSSH" "$T" 'cat > /data/mf-reader.sh' < "$HERE/mf-reader.sh" || exit 1
"$KSSH" "$T" 'cat > /home/root/.surf/script.js' < "$HERE/mf-probe.js" || exit 1
"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<EOF
echo "# buildinfo \$(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# \$(rauc status 2>&1 | grep 'Booted from')"
echo "# probe sha256 deployed \$(sha256sum < /home/root/.surf/script.js | cut -d' ' -f1)"
echo "# boot-start \$(cat /proc/sys/kernel/random/boot_id)"
rm -rf /home/root/.surf/cache /data/mf.log
systemctl restart kiosk
echo "# start-epoch \$(date +%s) \$(systemctl show -p NRestarts kiosk)"
echo "# vmstat-start \$(grep -E '^(pswpin|pswpout) ' /proc/vmstat | tr '\n' ' ')"
setsid nohup sh /data/mf-reader.sh /data/mf.log $SECS > /dev/null 2>&1 < /dev/null &
EOF
START=$(sed -n 's/^# start-epoch \([0-9]*\).*/\1/p' "$OUT")
[ -n "$START" ] || { echo "# START FAILED" >> "$OUT"; exit 1; }

sleep $((SECS + 60))

"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<EOF
echo "=== MF log ==="
cat /data/mf.log
echo "=== kiosk-soak samples since start-epoch ==="
awk -v s=$START '{ split(\$1, a, "="); if (a[2] >= s) print }' /data/kiosk-soak.log
N=\$(awk -v s=$START '{ split(\$1, a, "="); if (a[2] >= s) n++ } END { print n + 0 }' /data/kiosk-soak.log)
echo "=== kiosk-soak --summary \$N (samples since start-epoch) ==="
[ "\$N" -gt 0 ] && kiosk-soak.sh --summary "\$N"
echo "# boot-end \$(cat /proc/sys/kernel/random/boot_id)"
echo "# end \$(systemctl show -p NRestarts kiosk)"
echo "# vmstat-end \$(grep -E '^(pswpin|pswpout) ' /proc/vmstat | tr '\n' ' ')"
echo "=== /proc/pressure/memory ==="
cat /proc/pressure/memory
echo "=== kernel OOM lines since start-epoch ==="
journalctl -k --since @$START --no-pager | grep -iE 'out of memory|oom-kill|oom_reaper'
: > /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
echo "# restored: script.js \$(wc -c < /home/root/.surf/script.js) bytes, kiosk restarted"
EOF
echo "# complete $(date -u +%FT%TZ)" >> "$OUT"
