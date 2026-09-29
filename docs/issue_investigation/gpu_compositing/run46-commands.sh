#!/bin/sh
# Run 46 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Resolved via the task-id chain: line 11984 starts the capture (task bkgw1q1o7), staged to imperative-tour-587s-raw.txt at line 12054.


# --- transcript line 11984  2026-09-23T06:12:25.929Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p30_baseline.js
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> "sh -s" <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 600
export DISPLAY=:0
echo "=== IMPERATIVE TOUR (DJUeJLKg), clean config, 600s ==="
for id in $(xwininfo -root -children 2>/dev/null | grep -oE '0x[0-9a-f]+'); do
  xprop -len 12000 -id $id WM_NAME 2>/dev/null | grep -E 'BL\|'
done
echo "=== loadavg ==="; cat /proc/loadavg
echo "=== done ==="
EOF


# --- transcript line 12054  2026-09-23T06:28:45.566Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
T=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks
cp "$T/bvzgwcubo.output" ./freq-lever-P16-535s-raw.txt
cp "$T/bkgw1q1o7.output" ./imperative-tour-587s-raw.txt
echo "staged freq-lever + imperative-tour raw captures"
ls -1 freq-lever-P16-535s-raw.txt imperative-tour-587s-raw.txt fix1-benchmark-600s-raw.txt


# --- transcript line 12142  2026-09-23T06:44:54.735Z ---
cd /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
S=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
echo "=== derive_bl.py from gc-doc? ==="; ls -la "$S/derive_bl.py" 2>&1 | tail -1
# Run 46 display-validation screenshots (evidence the imperative render is pixel-correct + rotates)
cp "$S/imp-tour-shot1.png" ./imperative-tour-render-shot1.png 2>/dev/null && echo "staged shot1"
cp /home/tjwise/meta-wisekiosk/local/kiosk-20260923-021104.png ./imperative-tour-render-shot2-rotated.png 2>/dev/null && echo "staged shot2 (rotated)"
# Run 38 instrument-availability capture (CAP| payload) + Run 44 inspector (gc+census)
cat > ./cap-probe-raw.txt <<'CAP'
=== Run 38 capability probe (cap-probe.js), prod, bundle index-Mt2gvuKb.js ===
CAP|pm:NONE|FinalizationRegistry:function|WeakRef:function|gc:undefined|qMt:function|AppleWebKit/605.1.15
=== Run 38 FinalizationRegistry GC detector (p26_gc.js) — fin=0, callbacks never fired ===
GC2|118|f4864|big10|fin0|S[1.6:1445,2.7:1080,3.1:369,3.9:793,4.2:300,8.4:286,40.2:304,41:860,41.6:569,42:466]|G[]
CAP
echo "staged cap-probe-raw.txt (Run 38)"
cat > ./inspector-gc-census-raw.txt <<'INS'
=== Run 44 remote inspector (webkit-inspect.mjs), prod, WEBKIT_INSPECTOR_HTTP_SERVER, bundle index-Mt2gvuKb.js ===
--- gc 85s: Heap.startTracking -> Heap.garbageCollected events ---
{"seconds":85,"total":1,"full":1,"eden":0,"fullTimes":[7.08]}
(collections report type "full"; under tracking the collector is quiesced, so cadence is not the untracked cadence -- used only to confirm the collection TYPE, not frequency)
--- census: Heap.snapshot (HeapSnapshot v2, 20866 nodes), top classes by bytes ---
   247882 B     569   UnlinkedFunctionCodeBlock
   187938 B    2272   Object
   129285 B    3954   Function
    91695 B     376   Map
    84880 B    1061   UnlinkedFunctionExecutable
    75214 B    2651   string
    69200 B     865   FunctionExecutable
    66736 B    1257   JSLexicalEnvironment
    64256 B    2008   DOMAttributeGetterSetter
    60320 B     750   Structure
--- diff (profile-churn.mjs) over 30s: NO retained growth (transient churn, no leak) ---
INS
echo "staged inspector-gc-census-raw.txt (Run 44)"
ls -1 imperative-tour-render-*.png cap-probe-raw.txt inspector-gc-census-raw.txt 2>/dev/null
