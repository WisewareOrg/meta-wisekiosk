#!/bin/sh
# Run 48 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main session file 9253304a-ddb2-4c2c-827e-a05b0942ac7b.jsonl
# Commands are exactly as typed, in order, with their transcript line number and timestamp.
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH on all three arms' deploy+capture commands (12s -> line 13310, 6s -> line 13397,
# 8s -> line 13437) -- each is a single clean pass with no retries, and the 8s arm's own capture
# carries an R[] median of 8.000s, matching the README's cited value.
# Confidence: MEDIUM on how config.json returned to the schema default (no rotation_interval_seconds
# key) before the 8s arm. No explicit restore command (git checkout, or a cp from config.json.c2bak)
# was found between the 6s arm (line 13397) and the 8s arm's deploy (line 13437) -- the first check
# confirming the file was "clean" happens only afterward, at line 13495. This does not put which
# command drove the 8s arm in question (line 13437 is unambiguous and its capture matches), only the
# provenance of the environment it ran against. Not escalated, since the run itself ties to a
# command; noted here as the one point this recovery could not fully trace.

# --- transcript line 13231  2026-09-23T12:55:56.727Z ---
cp /home/tjwise/WiseKiosk/frontend/public/config.json /home/tjwise/WiseKiosk/frontend/public/config.json.c2bak && echo "backed up"


# --- transcript line 13294  2026-09-23T12:59:40.392Z ---
cd /home/tjwise/WiseKiosk
docker compose -f compose.dev.yaml up -d kiosk 2>&1 | tail -8
sleep 5
echo "=== status ==="
docker ps --filter name=kiosk --format '{{.Names}} | {{.Status}} | {{.Ports}}' 2>&1
echo "=== HTTP + served rotation ==="
python3 -c "
import urllib.request,json,time
for a in range(6):
    try:
        c=json.load(urllib.request.urlopen('http://<mirror>:8080/config.json?t='+str(time.time()),timeout=5))
        m=[x for x in c['modules'] if x['module']=='park_wait_times'][0]
        print('UP; served rotation =', m['options'].get('rotation_interval_seconds','ABSENT')); break
    except Exception as e:
        print('retry',a,type(e).__name__); time.sleep(3)
"


# --- transcript line 13299  2026-09-23T13:00:49.516Z ---
cd /home/tjwise/WiseKiosk
docker compose -f compose.dev.yaml up -d --force-recreate kiosk 2>&1 | tail -6
sleep 5
docker ps --filter name=kiosk --format '{{.Names}} | {{.Status}}' 2>&1
python3 -c "
import urllib.request,json,time
for a in range(6):
    try:
        c=json.load(urllib.request.urlopen('http://<mirror>:8080/config.json?t='+str(time.time()),timeout=5))
        m=[x for x in c['modules'] if x['module']=='park_wait_times'][0]
        print('UP; served rotation =', m['options'].get('rotation_interval_seconds','ABSENT')); break
    except Exception as e:
        print('retry',a,type(e).__name__); time.sleep(3)
"


# --- transcript line 13310  2026-09-23T13:01:20.948Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
echo "restarted, sleeping 600"
sleep 600
export DISPLAY=:0
echo "=== WM_NAME (BL) ==="
for id in $(xwininfo -root -children | grep '0x' | awk '{print $1}'); do
  xprop -len 9000 -id $id WM_NAME | grep 'BL|'
done
echo "LOAD $(cat /proc/loadavg)"
echo "MEM $(grep MemAvailable /proc/meminfo)"
echo "=== C2 DONE ==="
EOF


# --- transcript line 13384  2026-09-23T13:12:12.817Z ---
cd /home/tjwise/WiseKiosk
python3 - <<'PY'
import json,io
p="frontend/public/config.json"
s=open(p).read()
s2=s.replace('"rotation_interval_seconds": 12','"rotation_interval_seconds": 6')
# in-place truncate-write: preserves inode (does NOT rename), so the bind mount stays valid
with open(p,'w') as f:
    f.write(s2)
print("edited in place; rotation now:", [m['options'].get('rotation_interval_seconds') for m in json.loads(s2)['modules'] if m['module']=='park_wait_times'][0])
PY
sleep 1
python3 -c "import urllib.request,json,time; c=json.load(urllib.request.urlopen('http://<mirror>:8080/config.json?t='+str(time.time()),timeout=6)); m=[x for x in c['modules'] if x['module']=='park_wait_times'][0]; print('SERVED rotation =', m['options'].get('rotation_interval_seconds','ABSENT'))"


# --- transcript line 13397  2026-09-23T13:12:46.664Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
echo "restarted at 6s rotation, sleeping 600"
sleep 600
export DISPLAY=:0
echo "=== WM_NAME (BL) ==="
for id in $(xwininfo -root -children | grep '0x' | awk '{print $1}'); do
  xprop -len 9000 -id $id WM_NAME | grep 'BL|'
done
echo "LOAD $(cat /proc/loadavg)"
echo "MEM $(grep MemAvailable /proc/meminfo)"
echo "=== 6S DONE ==="
EOF


# --- transcript line 13437  2026-09-23T13:25:09.225Z ---
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -rf /home/root/.surf/cache
systemctl restart kiosk
echo "restarted at 8s (default), sleeping 600"
sleep 600
export DISPLAY=:0
echo "=== WM_NAME (BL) ==="
for id in $(xwininfo -root -children | grep '0x' | awk '{print $1}'); do
  xprop -len 9000 -id $id WM_NAME | grep 'BL|'
done
echo "LOAD $(cat /proc/loadavg)"
echo "MEM $(grep MemAvailable /proc/meminfo)"
echo "=== 8S DONE ==="
EOF
