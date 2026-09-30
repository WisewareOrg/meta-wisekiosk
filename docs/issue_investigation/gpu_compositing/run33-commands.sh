#!/bin/sh
# Run 33 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the named /tmp/shm.txt mapping (line 9485); the config-set command (line 9367) explicitly labels itself "compositing on, SHM buffers, tiled", matching the README's Run 33 configuration exactly.


# --- transcript line 9367  2026-09-22T22:10:59.088Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
cp /data/config/kiosk.conf /data/config/kiosk.conf.bak-preshm
: > /home/root/.surf/script.js
cat > /data/config/kiosk.conf <<'CONF'
KIOSK_URL=http://<mirror>:8080/
KIOSK_INSPECTOR=0
WEBKIT_FORCE_VBLANK_TIMER=1
WEBKIT_DMABUF_RENDERER_FORCE_SHM=1
WEBKIT_NICOSIA_PAINTING_THREADS=4
CONF
echo "-- new config (compositing on, SHM buffers, tiled) --"; cat /data/config/kiosk.conf
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 30
echo "-- health --"; systemctl is-active kiosk
w=$(pidof WebKitWebProcess); w=${w%% *}; echo "webproc=$w"
[ -n "$w" ] && { echo "-- gallium driver / SHM? --"; tr '\0' '\n' < /proc/$w/maps | grep -oE '(vc4|v3d|swrast)_dri\.so' | sort -u; echo "-- /dev/dri open? --"; ls -l /proc/$w/fd 2>&1 | grep -oE '/dev/dri/[a-z0-9]*' | sort -u; }
echo "-- painting threads present? --"; [ -n "$w" ] && ls /proc/$w/task | wc -l
EOF


# --- transcript line 9394  2026-09-22T22:12:36.079Z ---
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


# --- transcript line 9402  2026-09-22T22:17:53.749Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aoE 'MP\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bzpc5z3ta.output | tail -1 > /tmp/shm.txt
python3 - <<'PY'
import re
t=open('/tmp/shm.txt').read()
m=re.search(r'MP\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|H([\d.]+)\|B(.*)$', t.strip())
sec,f,av,mx,bt,H=m.groups()[:6]
h=[int(x) for x in H.split('.')]
tot=sum(h) or 1
labels=['<50','50-100','100-250','250-500','500-1k','1k-2k','>=2k']
print(f"TILED-SHM: window {sec}s  frames {f}  mean {av}ms (~{1000/int(av):.0f}fps)  max {mx}ms")
print(f"  >250ms deadline misses: {bt}  = {int(bt)/int(sec):.3f}/s")
for l,c in zip(labels,h):
    if c: print(f"    {l:>8}: {c:6d} ({100*c/tot:4.1f}%)")
print("\n  vs software (compositing-off) baseline: mean ~24ms, misses 0.04/s, max ~1500ms")
PY


# --- transcript line 9412  2026-09-22T22:21:13.541Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
cp /data/config/kiosk.conf.bak-preshm /data/config/kiosk.conf
: > /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 28
echo "-- config restored --"; cat /data/config/kiosk.conf
echo "-- bundle --"; grep -rhoE "index-[A-Za-z0-9_]+\.js" /home/root/.surf/cache | sort -u
systemctl is-active kiosk
EOF
tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1
