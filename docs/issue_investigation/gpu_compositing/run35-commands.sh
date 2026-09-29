#!/bin/sh
# Run 35 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Single clean pass: kiosk-launch patched to 640x480, deployed, captured to /tmp/r480.txt, then staged as res640x480-194s-raw.txt (lines 9617-9635).


# --- transcript line 9617  2026-09-22T23:53:39.040Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p7_min.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
# switch the kiosk-launch xrandr mode to 640x480 for this diagnostic
sed -i 's/--mode 1280x720/--mode 640x480/' /usr/bin/kiosk-launch
grep -n 'xrandr' /usr/bin/kiosk-launch
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 205
export DISPLAY=:0
echo "-- mode --"; xrandr 2>/dev/null | grep '\*'
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 20000 -id $id WM_NAME 2>/dev/null | grep 'MP|')
  [ -n "$t" ] && echo "$t"
done
true
EOF


# --- transcript line 9630  2026-09-22T23:57:17.792Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aE 'mode|1280|640' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b9qcsjcpl.output | grep -iE '\*|xrandr' | head
grep -aoE 'MP\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b9qcsjcpl.output | tail -1 > /tmp/r480.txt
python3 - <<'PY'
import re
t=open('/tmp/r480.txt').read()
m=re.search(r'MP\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|H([\d.]+)\|B(.*)$', t.strip())
sec,f,av,mx,bt,H,B=m.groups()
h=[int(x) for x in H.split('.')]; tot=sum(h) or 1
labels=['<50','50-100','100-250','250-500','500-1k','1k-2k','>=2k']
print(f"640x480: {sec}s frames {f} mean {av}ms (~{1000/int(av):.0f}fps) MAX {mx}ms  >250ms {bt} = {int(bt)/int(sec):.3f}/s")
for l,c in zip(labels,h):
    if c: print(f"   {l:>8}: {c:5d} ({100*c/tot:4.1f}%)")
print("\n  720p baseline: max ~1500ms, >250ms 0.04/s")
print("  architect predicted 640x480 -> ~190ms (under 250 deadline)")
PY


# --- transcript line 9635  2026-09-22T23:58:18.098Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
sed -i 's/--mode 640x480/--mode 1280x720/' /usr/bin/kiosk-launch
grep -n xrandr /usr/bin/kiosk-launch
: > /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 26
export DISPLAY=:0; echo "-- mode restored --"; xrandr 2>/dev/null | grep '\*'
systemctl is-active kiosk
EOF
tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1
# preserve this decisive capture
cp /tmp/r480.txt docs/issue_investigation/gpu_compositing/res640x480-194s-raw.txt
echo "saved res640x480 raw"
