#!/bin/bash
# run-soak.sh <ssh-target> <role> <out>
#
# The 1 h soak under cog: mf-probe.js deployed to /home/root/kiosk-probe.js, kiosk.conf backed up
# and KIOSK_PROBE=1 appended, cog's cache cleared, kiosk restarted. cog prints each title as
# "TITLE <title>", so every 30 s MF| sample lands in the kiosk journal. After 3600 s + 60 s it
# appends the journal's MF| lines since the start, kiosk-soak --summary over the samples taken since
# the start and those samples themselves, kiosk NRestarts, boot id and /proc/vmstat
# pswpin/pswpout at both ends, /proc/pressure/memory, and kernel OOM lines since the start; then
# it restores kiosk.conf, removes the probe and restarts kiosk. A kiosk.conf backup already on the
# board means an earlier run did not restore; the run refuses, exit 1.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; OUT=${3:?out}
SECS=3600
HERE=$(dirname "$(readlink -f "$0")")
KSSH=$(git -C "$HERE" rev-parse --show-toplevel)/tools/kiosk-ssh.sh
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture" >&2; exit 2; }

{
echo "# run-soak.sh role=$ROLE secs=$SECS"
echo "# harness $(git -C "$HERE" rev-parse HEAD)$(git -C "$HERE" diff --quiet HEAD -- . || echo " DIRTY")"
echo "# started $(date -u +%FT%TZ)"
echo "# probe sha256 local    $(sha256sum < "$HERE/mf-probe.js" | cut -d' ' -f1)"
} > "$OUT"
"$KSSH" "$T" 'cat > /home/root/kiosk-probe.js' < "$HERE/mf-probe.js" || exit 1
"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<'EOF' || exit 1
C=/data/config/kiosk.conf
if [ -e $C.wpe-bak ] || [ -e $C.wpe-absent ]; then
	echo "# REFUSED: a kiosk.conf backup exists -- an earlier run did not restore"; exit 1
fi
if [ -f $C ]; then cp -p $C $C.wpe-bak || exit 1; else : > $C.wpe-absent; fi
[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
echo 'KIOSK_PROBE=1' >> $C
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
echo "# probe sha256 deployed $(sha256sum < /home/root/kiosk-probe.js | cut -d' ' -f1)"
echo "# boot-start $(cat /proc/sys/kernel/random/boot_id)"
rm -rf /home/root/.cache/cog
systemctl restart kiosk
echo "# start-epoch $(date +%s) $(systemctl show -p NRestarts kiosk)"
echo "# vmstat-start $(grep -E '^(pswpin|pswpout) ' /proc/vmstat | tr '\n' ' ')"
EOF
START=$(sed -n 's/^# start-epoch \([0-9]*\).*/\1/p' "$OUT")
[ -n "$START" ] || { echo "# START FAILED" >> "$OUT"; exit 1; }

sleep $((SECS + 60))

"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<EOF
echo "=== journal MF| since start-epoch ==="
journalctl -u kiosk --since @$START -o cat --no-pager | grep 'MF|'
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
C=/data/config/kiosk.conf
if [ -f \$C.wpe-bak ]; then mv \$C.wpe-bak \$C; elif [ -e \$C.wpe-absent ]; then rm -f \$C \$C.wpe-absent; else echo "# NO BACKUP -- kiosk.conf left as found"; fi
rm -f /home/root/kiosk-probe.js
rm -rf /home/root/.cache/cog
systemctl restart kiosk
n=\$(grep -c '^KIOSK_PROBE' \$C 2>/dev/null)
echo "# restored: kiosk.conf KIOSK_PROBE lines \${n:-none, file absent}, kiosk restarted"
EOF
echo "# complete $(date -u +%FT%TZ)" >> "$OUT"
