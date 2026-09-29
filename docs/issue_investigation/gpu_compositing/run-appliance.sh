#!/bin/bash
# run-appliance.sh <ssh-target> <role> <probe.js> <prefix> <sleep-s> <xprop-len> <out>
#
# The Runs 26/41/48 capture, as recovered verbatim from the session that ran them
# (w6 recovery: run26-commands.sh, run41-commands.sh, run48-commands.sh), parameterised
# only for the target, the payload prefix it reads back (MP for p7_min.js, BL for
# p30_baseline.js / p31_rotcheck.js), the capture length and xprop's -len.
#
# The recorded sequence, unchanged:
#   deploy   cat > /home/root/.surf/script.js < <probe>
#   capture  rm -rf /home/root/.surf/cache; systemctl restart kiosk; sleep <s>;
#            DISPLAY=:0; for each top-level window: xprop -len <n> WM_NAME | grep '<prefix>|'
#            then loadavg and MemAvailable
#   restore  : > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk
#
# Added around it, none of which runs inside the capture window:
#   - R1 header: role, /etc/buildinfo's meta-wisekiosk line, booted slot, config.json sha256 and
#     its rotation_interval_seconds, kiosk.conf keys (KIOSK_URL masked), probe sha256 local and
#     as deployed.
#   - xrandr before deploy and after readback. Anything but 1280x720 live on either read marks the
#     run VOID (exit 3): the plan's rule for W10.
#   - the served bundle name, read from the WebKit cache after readback (Run 26a's recorded step).
#   - kiosk NRestarts after readback: a restart inside the window is recorded, not hidden.
# Deviation from the recorded text: xwininfo/xprop stderr is kept rather than sent to /dev/null,
# so a failed readback is visible in the capture instead of reading as an empty payload. The
# window-id scan is Run 26/48's `grep '0x' | awk '{print $1}'` (Run 41's `grep -oE` form also
# pulls hex fragments out of geometry and would put BadWindow noise into the capture). Its three
# xwininfo header lines also contain 0x, so three "Invalid window id format" lines appear in every
# capture; the recorded runs hid them with 2>/dev/null. They carry no payload.
# Recorded parameters: 26a sleep 180 len 20000 (MP); 26b 300/30000 (MP); 41 600/12000 (BL);
# 48-8s 600/9000 (BL).
#
# The output file is the committed capture. It names the board by <role>, never by address.
set -u
T=${1:?ssh-target}; ROLE=${2:?role}; PROBE=${3:?probe.js}; PFX=${4:?prefix}; SLEEP=${5:?sleep-s}
LEN=${6:?xprop-len}; OUT=${7:?out}
KSSH=$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel 2>/dev/null)/tools/kiosk-ssh.sh
[ -x "$KSSH" ] || KSSH=/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh
case "$PFX" in MP|BL) ;; *) echo "prefix must be MP or BL" >&2; exit 2 ;; esac
case "$SLEEP$LEN" in *[!0-9]*) echo "sleep and len are integers" >&2; exit 2 ;; esac
[ -f "$PROBE" ] || { echo "no probe $PROBE" >&2; exit 2; }
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture" >&2; exit 2; }

xr() { "$KSSH" "$T" 'DISPLAY=:0 xrandr' 2>&1; }
live720() { printf '%s\n' "$1" | grep -cE '^ +1280x720 +[0-9.]+\*' ; }

{
echo "# run-appliance.sh role=$ROLE probe=$(basename "$PROBE") prefix=$PFX sleep=$SLEEP len=$LEN"
echo "# started $(date -u +%FT%TZ)"
echo "# probe sha256 local    $(sha256sum < "$PROBE" | cut -d' ' -f1)"
"$KSSH" "$T" 'sh -s' <<'PRE'
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
echo "# config.json sha256 $(sha256sum /data/config/config.json | cut -d' ' -f1)"
sed 's/^\(KIOSK_URL=\).*/\1<masked>/; s/^/# kiosk.conf /' /data/config/kiosk.conf
PRE
# Read as Run 48 read it: modules[park_wait_times].options, parsed here (the board has no python).
"$KSSH" "$T" 'cat /data/config/config.json' | python3 -c 'import json,sys; c=json.load(sys.stdin); m=[x for x in c["modules"] if x["module"]=="park_wait_times"]; print("# park_wait_times.rotation_interval_seconds", m[0].get("options",{}).get("rotation_interval_seconds","ABSENT (schema default)") if m else "NO park_wait_times MODULE")'
} > "$OUT"

XR0=$(xr); printf '%s\n' "$XR0" | sed 's/^/# xrandr-before /' >> "$OUT"

"$KSSH" "$T" 'cat > /home/root/.surf/script.js' < "$PROBE" || { echo "# DEPLOY FAILED" >> "$OUT"; exit 1; }
echo "# probe sha256 deployed $("$KSSH" "$T" 'sha256sum < /home/root/.surf/script.js' | cut -d' ' -f1)" >> "$OUT"

echo "# capture start $(date -u +%FT%TZ)" >> "$OUT"
"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<EOF
rm -rf /home/root/.surf/cache
systemctl restart kiosk
echo "restarted, sleeping $SLEEP"
sleep $SLEEP
export DISPLAY=:0
echo "=== WM_NAME ($PFX) ==="
for id in \$(xwininfo -root -children | grep '0x' | awk '{print \$1}'); do
  xprop -len $LEN -id \$id WM_NAME | grep '$PFX|'
done
echo "LOAD \$(cat /proc/loadavg)"
echo "MEM \$(grep MemAvailable /proc/meminfo)"
echo "=== DONE ==="
EOF
echo "# capture end $(date -u +%FT%TZ)" >> "$OUT"

XR1=$(xr); printf '%s\n' "$XR1" | sed 's/^/# xrandr-after /' >> "$OUT"
"$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1 <<'POST'
echo "# bundle $(grep -rhoE 'index-[A-Za-z0-9_]+\.js' /home/root/.surf/cache | sort -u | tr '\n' ' ')"
echo "# kiosk $(systemctl show -p NRestarts -p ActiveEnterTimestamp kiosk | tr '\n' ' ')"
: > /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
echo "# restored: script.js $(wc -c < /home/root/.surf/script.js) bytes, kiosk restarted"
POST

n=$(grep -c "WM_NAME.*$PFX|" "$OUT")
if [ "$(live720 "$XR0")" -ne 1 ] || [ "$(live720 "$XR1")" -ne 1 ]; then
    echo "# VOID: 1280x720 not live before and after" >> "$OUT"; echo "VOID (display mode) -- $OUT"; exit 3
fi
[ "$n" -ge 1 ] || { echo "# NO PAYLOAD: no $PFX| line read back" >> "$OUT"; echo "no payload -- $OUT"; exit 1; }
echo "# complete $(date -u +%FT%TZ): $n payload line(s)" >> "$OUT"
echo "captured -> $OUT"
