#!/bin/sh
# Run 32 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the named /tmp/cont.txt mapping (line 9485).


# --- transcript line 9288  2026-09-22T21:39:52.234Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p7_min.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 305
n=$(grep -rl 'index-B8gPvD4g' /home/root/.surf/cache | wc -l); echo "new bundle refs: $n"
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 20000 -id $id WM_NAME 2>/dev/null | grep 'MP|')
  [ -n "$t" ] && echo "$t"
done
true
EOF


# --- transcript line 9296  2026-09-22T21:45:10.309Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aE 'new bundle refs' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bupoopr3h.output
grep -aoE 'MP\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bupoopr3h.output | tail -1 > /tmp/cont.txt
python3 - <<'PY'
import re
t=open('/tmp/cont.txt').read()
m=re.search(r'MP\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|H([\d.]+)\|B(.*)$', t.strip())
sec,f,av,mx,bt,H,B=m.groups()
print(f"CONTINUOUS ping-pong: {sec}s frames {f} mean {av}ms max {mx}ms  big>250ms {bt} = {int(bt)/int(sec):.3f}/s")
print("vs baseline (holds): 0.04/s at scroll-start (mod-8=2)")
pairs=[]
for e in B.split(','):
    mm=re.match(r'([\d.]+):(\d+)',e.strip().strip('"'))
    if mm: pairs.append((float(mm.group(1)),int(mm.group(2))))
steady=[(ts,ms) for ts,ms in pairs if ts>8]
print(f"steady big frames (t>8s): {len(steady)}  ->", [(round(ts,0),ms) for ts,ms in steady])
PY
