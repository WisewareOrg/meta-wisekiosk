#!/bin/sh
# Run 34 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the named /tmp/thr.txt mapping (line 9485); the config-set command (line 9430) explicitly sets WEBKIT_NICOSIA_PAINTING_THREADS=4 without compositing, matching the README's Run 34 configuration.


# --- transcript line 9430  2026-09-22T22:25:23.106Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
cp /data/config/kiosk.conf /data/config/kiosk.conf.bak-prethreads
: > /home/root/.surf/script.js
cat > /data/config/kiosk.conf <<'CONF'
KIOSK_URL=http://<mirror>:8080/
KIOSK_INSPECTOR=0
WEBKIT_FORCE_VBLANK_TIMER=1
WEBKIT_DISABLE_DMABUF_RENDERER=1
WEBKIT_NICOSIA_PAINTING_THREADS=4
CONF
echo "-- config (software path + painting threads) --"; cat /data/config/kiosk.conf
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 30
echo "-- health --"; systemctl is-active kiosk
w=$(pidof WebKitWebProcess); w=${w%% *}; echo "webproc threads: $(ls /proc/$w/task | wc -l)"
EOF


# --- transcript line 9434  2026-09-22T22:26:01.954Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p7_min.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 305
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 20000 -id $id WM_NAME 2>/dev/null | grep 'MP|')
  [ -n "$t" ] && echo "$t"
done
true
EOF


# --- transcript line 9447  2026-09-22T22:31:16.380Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aoE 'MP\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/blg1u2npl.output | tail -1 > /tmp/thr.txt
python3 - <<'PY'
import re
t=open('/tmp/thr.txt').read()
m=re.search(r'MP\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|H([\d.]+)', t.strip())
sec,f,av,mx,bt,H=m.groups()
print(f"PAINTING-THREADS (software path): {sec}s frames {f} mean {av}ms (~{1000/int(av):.0f}fps) max {mx}ms")
print(f"  >250ms misses: {bt} = {int(bt)/int(sec):.3f}/s")
print("  vs plain software prod: mean 24ms ~42fps, misses 0.04/s")
PY


# --- transcript line 9451  2026-09-22T22:31:25.753Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
cp /data/config/kiosk.conf.bak-prethreads /data/config/kiosk.conf
: > /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 26
echo "-- config --"; cat /data/config/kiosk.conf
echo "-- backups cleanup --"; rm -f /data/config/kiosk.conf.bak-preshm /data/config/kiosk.conf.bak-prethreads /data/config/kiosk.conf.bak-preinspect /data/config/kiosk.conf.bak-retest-20260922; ls /data/config/kiosk.conf.bak* 2>&1
systemctl is-active kiosk
EOF
tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1
