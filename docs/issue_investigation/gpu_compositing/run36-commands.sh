#!/bin/sh
# Run 36 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Single clean pass, p24_alloc.js deployed and read back via a direct grep of the background task's own output (line 9740), no retries found.


# --- transcript line 9730  2026-09-23T01:05:46.547Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
node --check p24_alloc.js && echo "syntax OK"


# --- transcript line 9733  2026-09-23T01:05:55.185Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < docs/issue_investigation/gpu_compositing/p24_alloc.js
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 445
export DISPLAY=:0
for id in $(xwininfo -root -children 2>/dev/null | grep '0x' | awk '{print $1}'); do
  t=$(xprop -len 20000 -id $id WM_NAME 2>/dev/null | grep 'AL|')
  [ -n "$t" ] && echo "$t"
done
true
EOF


# --- transcript line 9740  2026-09-23T01:13:35.563Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
grep -aoE 'AL\|[^"]*' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bzybvmmx8.output | tail -1 > alloc-pressure-raw.txt
cat alloc-pressure-raw.txt | cut -c1-200; echo
python3 - <<'PY'
import re
t=open('alloc-pressure-raw.txt').read()
m=re.search(r'AL\|(\d+)\|f(\d+)\|av(\d+)\|mx(\d+)\|BT(\d+)\|A:([\d.]+)\|B:([\d.]+)\|H([\d.]+)', t)
sec,f,av,mx,bt=m.group(1),m.group(2),m.group(3),m.group(4),m.group(5)
def arm(s):
    n,big,mean,mxx,alloc=[int(x) for x in s.split('.')]
    return n,big,mean,mxx,alloc
An,Ab,Am,Amx,Aa=arm(m.group(6))
Bn,Bb,Bm,Bmx,Ba=arm(m.group(7))
print(f"window {sec}s frames {f} overall mean {av}ms max {mx}ms  >250ms total {bt}")
print(f"\n{'arm':>10} {'frames':>7} {'>250ms':>7} {'rate/s':>8} {'mean':>6} {'max':>6} {'allocated':>9}")
print(f"{'A BASE':>10} {An:>7} {Ab:>7} {Ab/(An/ (int(f)/int(sec)) if An else 1):>8}")
# rate per second: big/ (arm-seconds). arm-seconds approx = n / overall_fps
fps=int(f)/int(sec)
Asec=An/fps if fps else 1; Bsec=Bn/fps if fps else 1
print(f"{'A BASE':>10} {An:>7} {Ab:>7} {Ab/Asec:>8.3f} {Am:>6} {Amx:>6} {Aa:>9}")
print(f"{'B ALLOC':>10} {Bn:>7} {Bb:>7} {Bb/Bsec:>8.3f} {Bm:>6} {Bmx:>6} {Ba:>9}")
print(f"\nALLOC vs BASE >250ms rate ratio: {(Bb/Bsec)/(Ab/Asec) if Ab else float('inf'):.2f}x  (landing: BASE allocated {Aa}, ALLOC allocated {Ba})")
PY


# --- transcript line 9745  2026-09-23T01:14:04.007Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -c ": > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk"'
sleep 25; tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -1
