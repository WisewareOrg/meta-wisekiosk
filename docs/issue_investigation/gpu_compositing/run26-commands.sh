#!/bin/sh
# Run 26 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Both arms resolved via the exact /tmp/mp.txt,/tmp/mp2.txt staging command (line 9485) that names each capture's destination filename explicitly.
# NOTE: Covers arms 26a (169s) and 26b (289s), both p7_min.js. Excluded as unrelated: L8608-8630 (reading the uncatalogued deployed-scroll-raw.txt capture from a prior session; not this run).

# --- transcript line 8658  2026-09-22T19:01:05.047Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p7_min.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 180
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 20000 -id $id WM_NAME 2>/dev/null | grep 'MP|')
  [ -n "$t" ] && echo "$t"
done
echo "-- bundle --"; grep -rhoE "index-[A-Za-z0-9_]+\.js" /home/root/.surf/cache | sort -u
true
EOF


# --- transcript line 8672  2026-09-22T19:04:17.994Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aoE 'MP\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bgmys2llj.output | tail -1 > /tmp/mp.txt
cat /tmp/mp.txt | cut -c1-120
grep -aE 'index-' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bgmys2llj.output
echo "=== histogram parse ==="
python3 - <<'PY'
import re
t=open('/tmp/mp.txt').read()
m=re.search(r'MP\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|H([\d.]+)',t)
if m:
    sec,f,av,mx,bt,H=m.groups()
    h=[int(x) for x in H.split('.')]
    tot=sum(h) or 1
    labels=['<50','50-100','100-250','250-500','500-1k','1k-2k','>=2k']
    print(f"window {sec}s  frames {f}  mean {av}ms (~{1000/int(av):.0f}fps)  max {mx}ms  big(>250ms) {bt} ({int(bt)/int(sec):.2f}/s)")
    for l,c in zip(labels,h):
        print(f"  {l:>8}: {c:6d} ({100*c/tot:5.1f}%)")
else:
    print("no MP match:", t[:200])
PY


# --- transcript line 8678  2026-09-22T19:04:31.435Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -c ": > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk"'
sleep 26
tools/kiosk-ssh.sh root@<prod> 'sh -c "export DISPLAY=:0; xrandr 2>/dev/null | grep \"\\*\"; systemctl is-active kiosk"'
tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1


# --- transcript line 8714  2026-09-22T19:13:11.898Z ---
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
true
EOF


# --- transcript line 8740  2026-09-22T19:18:25.029Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aoE 'MP\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/blcuz19to.output | tail -1 > /tmp/mp2.txt
python3 - <<'PY'
import re
t=open('/tmp/mp2.txt').read()
m=re.search(r'MP\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|H([\d.]+)\|B(.*)$', t.strip())
sec,f,av,mx,bt,H,B=m.groups()
print(f"window {sec}s frames {f} mean {av}ms max {mx}ms  big>250ms {bt} ({int(bt)/int(sec):.2f}/s)")
pairs=[]
for e in B.split(','):
    mm=re.match(r'([\d.]+):(\d+)',e.strip().strip('"'))
    if mm: pairs.append((float(mm.group(1)),int(mm.group(2))))
steady=[(ts,ms) for ts,ms in pairs if ts>8]   # drop page-load
print(f"\nsteady-state big frames (t>8s): {len(steady)}")
import statistics
mods=[round(ts%8,1) for ts,_ in steady]
print("mod-8s values:", mods)
inwin=sum(1 for x in mods if 1.5<=x<=3.0)
print(f"{inwin}/{len(mods)} land in [1.5,3.0]s mod 8  (scroll-start is t=2.0)")
PY


# --- transcript line 8745  2026-09-22T19:19:45.882Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -c ": > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk"'
sleep 25; tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1
