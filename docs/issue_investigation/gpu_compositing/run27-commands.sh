#!/bin/sh
# Run 27 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved the same way as Run 26, via the named /tmp/mp3.txt mapping.


# --- transcript line 8803  2026-09-22T19:28:34.265Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p7_min.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 300
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 30000 -id $id WM_NAME 2>/dev/null | grep 'MP|')
  [ -n "$t" ] && echo "$t"
done
echo "-- bundle --"; grep -rhoE "index-[A-Za-z0-9_]+\.js" /home/root/.surf/cache | sort -u
true
EOF


# --- transcript line 8817  2026-09-22T19:33:47.658Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aE 'index-' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/btdnb7abh.output
grep -aoE 'MP\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/btdnb7abh.output | tail -1 > /tmp/mp3.txt
python3 - <<'PY'
import re
t=open('/tmp/mp3.txt').read()
m=re.search(r'MP\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|H([\d.]+)\|B(.*)$', t.strip())
sec,f,av,mx,bt,H,B=m.groups()
print(f"STAGGERED: window {sec}s frames {f} mean {av}ms max {mx}ms  big>250ms {bt} ({int(bt)/int(sec):.3f}/s)")
pairs=[]
for e in B.split(','):
    mm=re.match(r'([\d.]+):(\d+)',e.strip().strip('"'))
    if mm: pairs.append((float(mm.group(1)),int(mm.group(2))))
steady=[(ts,ms) for ts,ms in pairs if ts>8]
mods=[round(ts%8,1) for ts,_ in steady]
print(f"steady big frames (t>8s): {len(steady)}   mod-8 values: {mods}")
inwin=sum(1 for x in mods if 1.5<=x<=3.0)
print(f"{inwin}/{len(mods)} still at the scroll-start window [1.5,3.0]")
print("\nvs BEFORE stagger: 0.04/s, 8/8 at mod-8=1.8-2.0")
PY


# --- transcript line 8857  2026-09-22T19:38:17.474Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
: > /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 28
echo "-- bundle --"; grep -rhoE "index-[A-Za-z0-9_]+\.js" /home/root/.surf/cache | sort -u
export DISPLAY=:0; echo "-- mode --"; xrandr 2>/dev/null | grep '\*'; echo "-- active --"; systemctl is-active kiosk
EOF
tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1
