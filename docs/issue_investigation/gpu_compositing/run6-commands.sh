#!/bin/sh
# Run 6 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: subagent agent-a45d0bf2462047d92.jsonl (lines 1-231)
# Timestamps: 2026-09-22T (see per-command timestamps)
# Commands are exactly as typed (full ordered sequence from the source subagent, minus
# nothing -- see MANIFEST.md for any run-boundary or exclusion notes).
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. Each of exp2 through exp6 plus diag/diag2 is a single deploy-and-read pass in
# this subagent, no retries found, and the label swaps between them (EX2->EX5->EX6) are the
# transcript's own mechanical transform, not inferred.



# --- L6  2026-09-22T00:28:38.940Z ---
ls /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/


# --- L8  2026-09-22T00:28:39.737Z ---
cat /home/tjwise/meta-wisekiosk/local/device-identity.md 2>&1 | head -60


# --- L11  2026-09-22T00:28:45.745Z ---
cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/framerate-settle.md


# --- L13  2026-09-22T00:28:46.367Z ---
cat /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh


# --- L16  2026-09-22T00:28:50.445Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad; wc -c $SP/script.js $SP/rafpoll.sh; echo ===SCRIPT===; cat $SP/script.js; echo ===POLL===; cat $SP/rafpoll.sh


# --- L19  2026-09-22T00:28:53.138Z ---
SP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad; echo "--- script.js"; cat $SP/script.js; echo "--- rafpoll.sh"; cat $SP/rafpoll.sh


# --- L22  2026-09-22T00:29:14.418Z ---
tools/kiosk-ssh.sh root@<prod> 'bash -s' <<'EOF'
date; uptime
systemctl is-active kiosk; systemctl show kiosk -p NRestarts -p ActiveEnterTimestamp
echo "--- ps"; ps w | grep -vE '\[' | tail -30
echo "--- script.js"; wc -c /home/root/.surf/script.js
echo "--- conf"; od -c /data/config/kiosk.conf | tail -20
echo "--- tmp probes"; ls -la /tmp/*.sh /tmp/*.log 2>&1 | head -20
EOF


# --- L25  2026-09-22T00:29:18.691Z ---
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
date; uptime
systemctl is-active kiosk; systemctl show kiosk -p NRestarts -p ActiveEnterTimestamp
echo "--- ps"; ps w | grep -v ']' | tail -30
echo "--- script.js"; wc -c /home/root/.surf/script.js
echo "--- conf"; cat /data/config/kiosk.conf
echo "--- tmp probes"; ls -la /tmp/ | head -30
EOF


# --- L28  2026-09-22T00:29:25.661Z ---
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "--- current script.js"; cat /home/root/.surf/script.js
echo "--- ls surf dir"; ls -la /home/root/.surf/
echo "--- tmp"; ls -la /tmp/
EOF


# --- L31  2026-09-22T00:29:36.177Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && curl -s -m 10 -o mirror-now.html -w '%{http_code} %{size_download}\n' http://<mirror>:8080/ && grep -o 'src="[^"]*"\|href="[^"]*"' mirror-now.html | head


# --- L33  2026-09-22T00:29:42.250Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && curl -s -m 20 -o now.css http://<mirror>:8080/assets/index-BK0v4JTg.css && curl -s -m 20 -o now.js http://<mirror>:8080/assets/index-D6VejKt2.js && wc -c now.css now.js && command grep -o 'marquee[a-zA-Z-]*' now.css | sort -u


# --- L35  2026-09-22T00:29:47.770Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'EOF'
import re
css=open('now.css').read()
# print rules mentioning marquee and surrounding
for m in re.finditer(r'[^{}]*marquee[^{}]*\{[^}]*\}', css):
    print(m.group(0).strip()[:600]); print('---')
EOF


# --- L38  2026-09-22T00:29:55.339Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && command grep -c 'pwt-marquee-phase' now.css now.js; python3 - <<'EOF'
import re
css=open('now.css').read()
names=sorted(set(re.findall(r'\.([a-zA-Z][a-zA-Z0-9_-]*)', css)))
print([n for n in names if not n.startswith('svelte')])
EOF


# --- L41  2026-09-22T00:30:02.931Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'EOF'
import re
css=open('now.css').read()
for sel in ['ride-name','\\.row','\\.card','park-wait-times','\\.seconds','\\.clock']:
    print('=====',sel)
    for m in re.finditer(r'[^{}]*'+sel+r'[^{}]*\{[^}]*\}', css):
        t=m.group(0).strip()
        print(t[:400]); print('-')
EOF


# --- L48  2026-09-22T00:32:02.065Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node --check exp-script.js && echo SYNTAX_OK; ls node_modules 2>/dev/null | head -20; which chromium chromium-browser google-chrome 2>&1 | head


# --- L50  2026-09-22T00:32:07.625Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && ls ~/.cache/ms-playwright 2>/dev/null; node -e "const p=require('playwright-core');console.log(p.chromium.executablePath())" 2>&1 | tail -2


# --- L53  2026-09-22T00:32:19.528Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && cat > smoke.mjs <<'EOF'
import { chromium } from 'playwright-core';
import fs from 'fs';
let src = fs.readFileSync('exp-script.js','utf8');
src = src.replace('WARM = 30000, SETTLE = 5000','WARM = 3000, SETTLE = 600')
         .replace(/ms: 20000/g,'ms: 1500').replace(/ms: 12000/g,'ms: 1500')
         .replace('}, 3000);','}, 500);');
const b = await chromium.launch({ executablePath: process.env.CHROME });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
await p.goto('http://<mirror>:8080/', { waitUntil: 'load' });
await p.evaluate(src);
for (let i=0;i<40;i++){ await p.waitForTimeout(1000); const t=await p.title(); if(i%5===0||t.includes('st=done')) console.log(i, t); if(t.includes('st=done')) break; }
console.log('FINAL:', await p.title());
await b.close();
EOF
CHROME=/home/tjwise/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome node smoke.mjs 2>&1 | tail -20


# --- L55  2026-09-22T00:32:24.253Z ---
ls /home/tjwise/.cache/ms-playwright/chromium-1228/ /home/tjwise/.cache/ms-playwright/chromium_headless_shell-1243/ 2>&1 | head -20


# --- L57  2026-09-22T00:32:29.562Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && CHROME=/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome node smoke.mjs 2>&1 | tail -20


# --- L63  2026-09-22T00:33:32.069Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && sed -i 's/> 4000) { apply/> 3000) { apply/g' exp-script.js && node --check exp-script.js && CHROME=/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome node smoke.mjs 2>&1 | tail -2


# --- L66  2026-09-22T00:34:18.382Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'PY'
import re
p='exp-script.js'; s=open(p).read()
s=s.replace("""        for (k = 0; k < ALLPROP.length; k++) els[j].style.removeProperty(ALLPROP[k]);""",
"""        for (k = 0; k < ALLPROP.length; k++) els[j].style.removeProperty(ALLPROP[k]);
        els[j].__phid = null;""")
s=s.replace("""      if (els[i].style.getPropertyValue(p.prop) !== p.val) {
        els[i].style.setProperty(p.prop, p.val, 'important');
        c++;
      }""",
"""      if (els[i].__phid !== p.id) {
        els[i].style.setProperty(p.prop, p.val, 'important');
        els[i].__phid = p.id;
        c++;
      }""")
s=s.replace("""      if (els[i].style.getPropertyValue(p.prop) === p.val) {""",
"""      if (els[i].__phid === p.id) {""")
open(p,'w').write(s)
PY
node --check exp-script.js && CHROME=/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome node smoke.mjs 2>&1 | tail -1


# --- L70  2026-09-22T00:35:00.710Z ---
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
cp /home/root/.surf/script.js /tmp/script.js.prev-stagger
: > /home/root/.surf/script.js
wc -c /home/root/.surf/script.js
systemctl restart kiosk
sleep 20
systemctl is-active kiosk
ps w | grep -E 'surf|WebKitWebProcess|X :0' | grep -v grep
echo "--- orphan check (loops)"; ps w | grep -E '\.sh|awk|sleep' | grep -v grep
EOF


# --- L73  2026-09-22T00:35:26.822Z ---
KIOSK_HOST=root@<prod> tools/kiosk-render-check.sh 2>&1 | tail -15


# --- L75  2026-09-22T00:35:29.896Z ---
tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -15


# --- L78  2026-09-22T00:35:46.267Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && /home/tjwise/meta-wisekiosk/tools/kiosk-screenshot.sh root@<prod> baseline-clean.png 2>&1 | tail -6


# --- L81  2026-09-22T00:36:12.482Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && sleep 45 && /home/tjwise/meta-wisekiosk/tools/kiosk-screenshot.sh root@<prod> baseline-clean2.png 2>&1 | tail -4


# --- L85  2026-09-22T00:37:23.182Z ---
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
date
echo "--- milestones"; tail -25 /var/log/surf-milestones.log
echo "--- can device reach mirror"; wget -S -O /tmp/idx.html -T 10 http://<mirror>:8080/ 2>&1 | tail -12; wc -c /tmp/idx.html
echo "--- procs"; ps w | grep -E 'surf|WebKit|X :0' | grep -v grep
echo "--- journal kiosk"; journalctl -u kiosk -n 25 --no-pager
EOF


# --- L88  2026-09-22T00:37:37.847Z ---
tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
export DISPLAY=:0
xwininfo -root -children 2>&1 | head -20
echo "--- titles"
for id in $(xwininfo -root -children | awk '/^     0x/{print $1}'); do echo "$id: $(xprop -id $id WM_NAME 2>&1)"; done
EOF


# --- L91  2026-09-22T00:37:48.419Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && command grep -nE 'import|xwd|fb0|DISPLAY' /home/tjwise/meta-wisekiosk/tools/kiosk-screenshot.sh | head -20


# --- L93  2026-09-22T00:37:53.602Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && tools_out=$(tools/kiosk-ssh.sh 2>/dev/null); /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF' > fb0now.b64
dd if=/dev/fb0 bs=1024 count=8100 2>/dev/null | gzip -c | base64 -w0
EOF
wc -c fb0now.b64


# --- L95  2026-09-22T00:37:58.206Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF' > fb0now.b64
fbset -i | grep -E 'geometry|mode|line'
dd if=/dev/fb0 bs=1024 count=8100 | gzip -c | base64 -w0
EOF
wc -c fb0now.b64; head -c 200 fb0now.b64


# --- L98  2026-09-22T00:38:10.782Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
export DISPLAY=:0
echo "--- fb0 stripe md5s (uniform => identical)"
for s in 100 500 1000 1500 2000 3000; do echo -n "$s "; dd if=/dev/fb0 bs=4096 skip=$s count=1 2>&1 | md5sum; done
echo "--- import surf window"
import -window 0x600002 /tmp/w.png && identify -format '%w x %h  min=%[min] max=%[max] mean=%[mean]\n' /tmp/w.png
echo "--- import root"
import -window root /tmp/r.png && identify -format '%w x %h  min=%[min] max=%[max] mean=%[mean]\n' /tmp/r.png
EOF


# --- L101  2026-09-22T00:39:29.337Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && /home/tjwise/meta-wisekiosk/tools/kiosk-screenshot.sh root@<prod> baseline-clean3.png 2>&1 | tail -3; /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'top -b -n1 | head -12'


# --- L107  2026-09-22T00:40:08.879Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'top -b -n1 | sed -n "1,12p"'


# --- L114  2026-09-22T00:40:42.704Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node --check diag-script.js && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlPath="$HOME/.ssh/kiosk-%C" diag-script.js root@<prod>:/home/root/.surf/script.js && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js
systemctl restart kiosk
sleep 35
export DISPLAY=:0
for id in $(xwininfo -root -children | awk '/^     0x/{print $1}'); do xprop -id $id WM_NAME; done
EOF


# --- L118  2026-09-22T00:41:40.573Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && for u in / /assets/index-D6VejKt2.js /assets/index-BK0v4JTg.css; do echo "== $u"; curl -sI -m 10 "http://<mirror>:8080$u" | command grep -iE 'last-modified|content-length|content-type'; done; echo "== index.html"; cat mirror-now.html


# --- L122  2026-09-22T00:42:12.852Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'PY'
s=open('diag-script.js').read()
add = """  window.onerror = function (m, f, l) { if (E.length < 200) E += '|ONERR:' + String(m).slice(0, 80) + '@' + String(f || '').split('/').pop() + ':' + l; };
  setTimeout(function () {
    var sc = document.querySelector('script[type=module]');
    var src = sc ? sc.getAttribute('src') : null;
    if (!src) { E += '|NOSCRIPTTAG'; return; }
    fetch(src).then(function (r) { E += '|FETCH' + r.status + ':' + r.headers.get('content-type'); return r.text(); })
      .then(function (t) { E += ':len' + t.length; })
      .catch(function (e) { E += '|FETCHFAIL:' + String(e && e.message || e).slice(0, 60); });
    import(src).then(function () { E += '|IMPORT_OK'; },
      function (e) { E += '|IMPORT_FAIL:' + String(e && e.message || e).slice(0, 100); });
  }, 8000);
"""
s = s.replace("  setInterval(function () {", add + "  setInterval(function () {",1)
open('diag2-script.js','w').write(s)
PY
node --check diag2-script.js && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlPath="$HOME/.ssh/kiosk-%C" diag2-script.js root@<prod>:/home/root/.surf/script.js && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js
cat /proc/sys/kernel/random/entropy_avail
systemctl restart kiosk
sleep 40
export DISPLAY=:0
xprop -id 0x600002 WM_NAME
sleep 20
xprop -id 0x600002 WM_NAME
EOF


# --- L126  2026-09-22T00:43:28.180Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && echo "== index.html now"; curl -s -m 10 http://<mirror>:8080/ ; echo "== headers"; curl -sI -m 10 http://<mirror>:8080/ | command grep -iE 'last-modified|content-length'; echo "== old bundle"; curl -s -o /dev/null -w '%{http_code} %{size_download}\n' -m 10 http://<mirror>:8080/assets/index-D6VejKt2.js; echo "== body of old bundle req"; curl -s -m 10 http://<mirror>:8080/assets/index-D6VejKt2.js


# --- L136  2026-09-22T00:45:17.524Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "--- surf cache tree"
du -sh /home/root/.surf/cache; find /home/root/.surf/cache -type f | wc -l
echo "--- any bundle hashes referenced in cache"
grep -roha 'index-[A-Za-z0-9_-]\{8\}\.\(js\|css\)' /home/root/.surf/cache 2>&1 | sort | uniq -c | sort -rn
echo "--- what the device gets for the CURRENT bundle path, via wget (bypasses webkit cache)"
wget -S -O /dev/null -T 10 http://<mirror>:8080/assets/index-D6VejKt2.js 2>&1 | grep -E 'HTTP/|Length'
EOF


# --- L140  2026-09-22T00:45:45.986Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && echo "== OLD hash from the device's webkit cache, asked of the mirror:"; curl -s -o old.txt -w 'status=%{http_code} bytes=%{size_download} type=%{content_type}\n' -m 10 http://<mirror>:8080/assets/index-BUwpCJwM.js; wc -c old.txt; cat old.txt; echo "== cache-control on index.html:"; curl -sI -m 10 http://<mirror>:8080/ | command grep -iE 'cache-control|etag|expires|last-modified|age' ; echo "(no cache-control line above = none sent)"


# --- L144  2026-09-22T00:46:05.295Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'PY'
p='exp-script.js'; s=open(p).read()
s=s.replace("var WARM = 30000, SETTLE = 5000;","var WARM = 45000, SETTLE = 5000;")
s=s.replace("      if (now - T0 >= WARM) {","      if (now - T0 >= WARM && q('.card').length > 0 && q('.ride-name').length > 0) {")
s=s.replace("""    document.title = 'EXP s' + t + ' n' + n + ' st=' + state + ' ph=' + cur +""",
"""    document.title = 'EXP s' + t + ' n' + n + ' st=' + state + ' ph=' + cur +
      ' app[all=' + document.querySelectorAll('*').length + ',card=' + q('.card').length +
      ',mq=' + q('.ride-name-text.marquee').length + ',ss=' + document.styleSheets.length + ']' +""")
open(p,'w').write(s)
PY
node --check exp-script.js && command grep -nE 'WARM =|q\(.\.card.\).length > 0|app\[all' exp-script.js


# --- L146  2026-09-22T00:46:14.945Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && CHROME=/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome node -e "
const fs=require('fs');let s=fs.readFileSync('exp-script.js','utf8');
s=s.replace('WARM = 45000, SETTLE = 5000','WARM = 2000, SETTLE = 400').replace(/ms: 20000/g,'ms: 1200').replace(/ms: 12000/g,'ms: 1200').replace('}, 3000);','}, 500);');
fs.writeFileSync('exp-smoke.js',s);" && node -e "
const {chromium}=require('playwright-core');(async()=>{
const b=await chromium.launch({executablePath:process.env.CHROME});
const p=await b.newPage({viewport:{width:1920,height:1080}});
await p.goto('http://<mirror>:8080/',{waitUntil:'load'});
await p.evaluate(require('fs').readFileSync('exp-smoke.js','utf8'));
for(let i=0;i<40;i++){await p.waitForTimeout(1000);const t=await p.title();if(t.includes('st=done')){console.log(t);break;}if(i===2)console.log('early:',t.slice(0,140));}
await b.close();})()" 2>&1 | tail -3


# --- L150  2026-09-22T00:46:48.710Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlPath="$HOME/.ssh/kiosk-%C" exp-script.js root@<prod>:/home/root/.surf/script.js && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js
echo "--- cache before"; du -sh /home/root/.surf/cache; grep -roha 'index-[A-Za-z0-9_-]\{8\}\.js' /home/root/.surf/cache | sort -u
rm -rf /home/root/.surf/cache
echo "--- cache after"; ls -la /home/root/.surf/
systemctl restart kiosk
sleep 40
export DISPLAY=:0
xprop -id 0x600002 WM_NAME
EOF


# --- L156  2026-09-22T00:48:12.138Z ---
/home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
export DISPLAY=:0
for i in 1 2 3 4 5; do sleep 80; echo "-- t=$(date +%H:%M:%S)"; xprop -id 0x600002 WM_NAME; done
EOF


# --- L158  2026-09-22T00:59:30.550Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && /home/tjwise/meta-wisekiosk/tools/kiosk-screenshot.sh root@<prod> run1-end.png 2>&1 | tail -3; /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'cat /proc/loadavg; grep -c . /proc/stat; top -b -n1 | sed -n "2,9p"'


# --- L164  2026-09-22T01:01:09.435Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node --check exp2-script.js && node -e "
const fs=require('fs');let s=fs.readFileSync('exp2-script.js','utf8');
s=s.replace('WARM = 40000, SETTLE = 4000, MEAS = 15000','WARM = 2000, SETTLE = 400, MEAS = 1500').replace('}, 3000);','}, 500);');
fs.writeFileSync('exp2-smoke.js',s);
const {chromium}=require('playwright-core');(async()=>{
const b=await chromium.launch({executablePath:'/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080}});
await p.goto('http://<mirror>:8080/',{waitUntil:'load'});
await p.evaluate(s);
for(let i=0;i<40;i++){await p.waitForTimeout(1000);const t=await p.title();if(t.includes('st=done')){console.log(t);break;}}
await b.close();})()" 2>&1 | tail -3


# --- L166  2026-09-22T01:01:56.697Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlPath="$HOME/.ssh/kiosk-%C" exp2-script.js root@<prod>:/home/root/.surf/script.js && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 25
export DISPLAY=:0
XP=$(pgrep -f '^X :0'); WK=$(pgrep -f WebKitWebProcess)
echo "pids X=$XP WK=$WK  CLK=$(getconf CLK_TCK)"
i=0
while [ $i -lt 28 ]; do
  L=$(cut -d' ' -f1 /proc/loadavg)
  XC=$(awk '{print $14+$15}' /proc/$XP/stat)
  WC=$(awk '{print $14+$15}' /proc/$WK/stat)
  T=$(xprop -id 0x600002 WM_NAME | cut -c1-70)
  echo "$(date +%s) load=$L X=$XC WK=$WC $T"
  i=$((i+1)); sleep 10
done
echo "=== FINAL TITLE ==="
xprop -id 0x600002 WM_NAME
EOF


# --- L169  2026-09-22T01:02:07.706Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlPath="$HOME/.ssh/kiosk-%C" exp2-script.js root@<prod>:/home/root/.surf/script.js && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 25
export DISPLAY=:0
XP=$(ps w | awk '/X :0 vt1/ && !/awk/ {print $1; exit}')
WK=$(ps w | awk '/WebKitWebProcess/ && !/awk/ {print $1; exit}')
echo "pids X=$XP WK=$WK CLK=$(getconf CLK_TCK)"
i=0
while [ $i -lt 28 ]; do
  L=$(cut -d' ' -f1 /proc/loadavg)
  XC=$(awk '{print $14+$15}' /proc/$XP/stat)
  WC=$(awk '{print $14+$15}' /proc/$WK/stat)
  T=$(xprop -id 0x600002 WM_NAME | cut -c1-72)
  echo "$(date +%s) load=$L X=$XC WK=$WC $T"
  i=$((i+1)); sleep 10
done
echo "=== FINAL TITLE ==="
xprop -id 0x600002 WM_NAME
EOF


# --- L173  2026-09-22T01:11:52.443Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node --check exp3-script.js && node -e "
const fs=require('fs');let s=fs.readFileSync('exp3-script.js','utf8');
s=s.replace('WARM = 40000, SETTLE = 4000, MEAS = 12000','WARM = 2000, SETTLE = 400, MEAS = 1500').replace('}, 3000);','}, 500);');
const {chromium}=require('playwright-core');(async()=>{
const b=await chromium.launch({executablePath:'/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080}});
await p.goto('http://<mirror>:8080/',{waitUntil:'load'});
await p.evaluate(s);
for(let i=0;i<30;i++){await p.waitForTimeout(1000);const t=await p.title();if(t.includes('st=done')){console.log(t);break;}}
console.log('probe removed:', await p.evaluate(()=>!document.getElementById('pwtprobe')), '| app display:', await p.evaluate(()=>document.getElementById('app').style.display||'(unset)'));
await b.close();})()" 2>&1 | tail -3


# --- L178  2026-09-22T01:12:57.807Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlPath="$HOME/.ssh/kiosk-%C" exp3-script.js root@<prod>:/home/root/.surf/script.js && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 25
export DISPLAY=:0
XP=$(ps w | awk '/X :0 vt1/ && !/awk/ {print $1; exit}')
WK=$(ps w | awk '/WebKitWebProcess/ && !/awk/ {print $1; exit}')
echo "pids X=$XP WK=$WK"
i=0
while [ $i -lt 18 ]; do
  L=$(cut -d' ' -f1 /proc/loadavg)
  XC=$(awk '{print $14+$15}' /proc/$XP/stat)
  WC=$(awk '{print $14+$15}' /proc/$WK/stat)
  T=$(xprop -id 0x600002 WM_NAME | cut -c1-58)
  echo "$(date +%s) load=$L X=$XC WK=$WC $T"
  i=$((i+1)); sleep 8
done
echo "=== FINAL ==="
xprop -id 0x600002 WM_NAME
EOF


# --- L184  2026-09-22T01:17:14.221Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node --check exp4-script.js && node -e "
const fs=require('fs');let s=fs.readFileSync('exp4-script.js','utf8');
s=s.replace('WARM = 40000, SETTLE = 3000, MEAS = 10000','WARM = 2000, SETTLE = 300, MEAS = 1000').replace('}, 3000);','}, 400);');
const {chromium}=require('playwright-core');(async()=>{
const b=await chromium.launch({executablePath:'/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080}});
await p.goto('http://<mirror>:8080/',{waitUntil:'load'});
await p.evaluate(s);
for(let i=0;i<50;i++){await p.waitForTimeout(1000);const t=await p.title();if(t.includes('st=done')){console.log(t);break;}}
console.log('leftover display:none count:', await p.evaluate(()=>document.querySelectorAll('[style*=\"display\"]').length));
await b.close();})()" 2>&1 | tail -3


# --- L187  2026-09-22T01:17:48.523Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'PY'
p='exp4-script.js'; s=open(p).read()
old = s[s.index("  function build() {"):s.index("  function cs(el, prop) {")]
new = """  function build() {
    var app = document.getElementById('app');
    if (!app) return false;
    var root = app;
    while (root.children.length === 1) root = root.children[0];
    var top = [], i, j;
    for (i = 0; i < root.children.length; i++) top.push({ el: root.children[i], path: 's' + i });
    var cand = top.slice();
    for (i = 0; i < top.length && cand.length < 8; i++) {
      var kids = top[i].el.children;
      for (j = 0; j < kids.length && cand.length < 8; j++) cand.push({ el: kids[j], path: top[i].path + '>' + j });
    }
    if (!cand.length) return false;
    PH.push({ id: 'b0', el: null, lab: '-' });
    for (i = 0; i < cand.length; i++) {
      PH.push({ id: 'h' + i, el: cand[i].el, lab: cand[i].path + '=' + label(cand[i].el) });
      PH.push({ id: 'b' + (i + 1), el: null, lab: '-' });
    }
    return true;
  }

"""
s = s.replace(old, new)
open(p,'w').write(s)
PY
node --check exp4-script.js && node -e "
const fs=require('fs');let s=fs.readFileSync('exp4-script.js','utf8');
s=s.replace('WARM = 40000, SETTLE = 3000, MEAS = 10000','WARM = 2000, SETTLE = 250, MEAS = 700').replace('}, 3000);','}, 400);');
const {chromium}=require('playwright-core');(async()=>{
const b=await chromium.launch({executablePath:'/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080}});
await p.goto('http://<mirror>:8080/',{waitUntil:'load'});
await p.evaluate(s);
for(let i=0;i<60;i++){await p.waitForTimeout(1000);const t=await p.title();if(t.includes('st=done')){console.log(t);break;}}
console.log('leftover:', await p.evaluate(()=>document.querySelectorAll('[style*=\"display\"]').length));
await b.close();})()" 2>&1 | tail -3


# --- L190  2026-09-22T01:18:18.609Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlPath="$HOME/.ssh/kiosk-%C" exp4-script.js root@<prod>:/home/root/.surf/script.js && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 25
export DISPLAY=:0
XP=$(ps w | awk '/X :0 vt1/ && !/awk/ {print $1; exit}')
WK=$(ps w | awk '/WebKitWebProcess/ && !/awk/ {print $1; exit}')
echo "pids X=$XP WK=$WK"
i=0
while [ $i -lt 26 ]; do
  L=$(cut -d' ' -f1 /proc/loadavg)
  XC=$(awk '{print $14+$15}' /proc/$XP/stat)
  WC=$(awk '{print $14+$15}' /proc/$WK/stat)
  T=$(xprop -id 0x600002 WM_NAME | cut -c1-52)
  echo "$(date +%s) load=$L X=$XC WK=$WC $T"
  i=$((i+1)); sleep 8
done
echo "=== FINAL ==="
xprop -id 0x600002 WM_NAME
EOF


# --- L193  2026-09-22T01:22:58.690Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'PY'
import re
css=open('now.css').read()
print("== all @keyframes:"); print(re.findall(r'@keyframes\s+([A-Za-z0-9_-]+)', css))
print("== all rules with animation/transition/will-change:")
for m in re.finditer(r'[^{}]*\{[^}]*(?:animation|transition|will-change)[^}]*\}', css):
    print(m.group(0).strip()[:300]); print('-')
PY


# --- L197  2026-09-22T01:23:42.055Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'PY'
s=open('exp2-script.js').read()
s=s.replace("""  var PH = [
    { id: 'b0', sel: null, prop: null, val: null },
    { id: 'P1', sel: '#app', prop: 'display', val: 'none' },
    { id: 'b1', sel: null, prop: null, val: null },
    { id: 'P2', sel: '.ride-name', prop: 'contain', val: 'paint' },
    { id: 'b2', sel: null, prop: null, val: null },
    { id: 'P3', sel: '.ride-name-text.marquee', prop: 'animation', val: 'none' },
    { id: 'b3', sel: null, prop: null, val: null },
    { id: 'P4', sel: '#app', prop: 'visibility', val: 'hidden' },
    { id: 'b4', sel: null, prop: null, val: null }
  ];

  var ALLSEL = ['#app', '.ride-name', '.ride-name-text', '.row', '.card'];
  var ALLPROP = ['contain', 'display', 'visibility', 'animation', 'will-change'];""",
"""  var PH = [
    { id: 'b0', sel: null, prop: null, val: null },
    { id: 'S1', sel: '.seconds', prop: 'display', val: 'none' },
    { id: 'b1', sel: null, prop: null, val: null },
    { id: 'S2', sel: '.clock', prop: 'display', val: 'none' },
    { id: 'b2', sel: null, prop: null, val: null },
    { id: 'S3', sel: '.ride-name-text', prop: 'display', val: 'none' },
    { id: 'b3', sel: null, prop: null, val: null },
    { id: 'S4', sel: '.wait', prop: 'display', val: 'none' },
    { id: 'b4', sel: null, prop: null, val: null }
  ];

  var ALLSEL = ['.seconds', '.clock', '.ride-name-text', '.wait'];
  var ALLPROP = ['display'];""")
s=s.replace("'EX2 s'","'EX5 s'").replace("'EX2 ERR '","'EX5 ERR '")
s=s.replace("MEAS = 15000","MEAS = 12000")
open('exp5-script.js','w').write(s)
PY
node --check exp5-script.js && node -e "
const fs=require('fs');let s=fs.readFileSync('exp5-script.js','utf8');
s=s.replace('WARM = 40000, SETTLE = 4000, MEAS = 12000','WARM = 2000, SETTLE = 300, MEAS = 900').replace('}, 3000);','}, 400);');
const {chromium}=require('playwright-core');(async()=>{
const b=await chromium.launch({executablePath:'/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080}});
await p.goto('http://<mirror>:8080/',{waitUntil:'load'});
await p.evaluate(s);
for(let i=0;i<40;i++){await p.waitForTimeout(1000);const t=await p.title();if(t.includes('st=done')){console.log(t);break;}}
console.log('leftover:', await p.evaluate(()=>document.querySelectorAll('[style*=\"display\"]').length));
await b.close();})()" 2>&1 | tail -3


# --- L199  2026-09-22T01:24:10.689Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlPath="$HOME/.ssh/kiosk-%C" exp5-script.js root@<prod>:/home/root/.surf/script.js && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 25
export DISPLAY=:0
XP=$(ps w | awk '/X :0 vt1/ && !/awk/ {print $1; exit}')
WK=$(ps w | awk '/WebKitWebProcess/ && !/awk/ {print $1; exit}')
echo "pids X=$XP WK=$WK"
i=0
while [ $i -lt 24 ]; do
  L=$(cut -d' ' -f1 /proc/loadavg)
  XC=$(awk '{print $14+$15}' /proc/$XP/stat)
  WC=$(awk '{print $14+$15}' /proc/$WK/stat)
  T=$(xprop -id 0x600002 WM_NAME | cut -c1-48)
  echo "$(date +%s) load=$L X=$XC WK=$WC $T"
  i=$((i+1)); sleep 8
done
echo "=== FINAL ==="
xprop -id 0x600002 WM_NAME
EOF


# --- L203  2026-09-22T01:28:40.071Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'PY'
s=open('exp2-script.js').read()
s=s.replace("""  var PH = [
    { id: 'b0', sel: null, prop: null, val: null },
    { id: 'P1', sel: '#app', prop: 'display', val: 'none' },
    { id: 'b1', sel: null, prop: null, val: null },
    { id: 'P2', sel: '.ride-name', prop: 'contain', val: 'paint' },
    { id: 'b2', sel: null, prop: null, val: null },
    { id: 'P3', sel: '.ride-name-text.marquee', prop: 'animation', val: 'none' },
    { id: 'b3', sel: null, prop: null, val: null },
    { id: 'P4', sel: '#app', prop: 'visibility', val: 'hidden' },
    { id: 'b4', sel: null, prop: null, val: null }
  ];

  var ALLSEL = ['#app', '.ride-name', '.ride-name-text', '.row', '.card'];
  var ALLPROP = ['contain', 'display', 'visibility', 'animation', 'will-change'];""",
"""  var PH = [
    { id: 'b0', sel: null, prop: null, val: null },
    { id: 'T1', sel: '.seconds', prop: 'contain', val: 'layout paint' },
    { id: 'b1', sel: null, prop: null, val: null },
    { id: 'T2', sel: '.clock', prop: 'contain', val: 'layout paint' },
    { id: 'b2', sel: null, prop: null, val: null },
    { id: 'T3', sel: '.seconds', prop: 'font-variant-numeric', val: 'tabular-nums' },
    { id: 'b3', sel: null, prop: null, val: null },
    { id: 'T4', sel: '.seconds', prop: 'visibility', val: 'hidden' },
    { id: 'b4', sel: null, prop: null, val: null }
  ];

  var ALLSEL = ['.seconds', '.clock'];
  var ALLPROP = ['contain', 'font-variant-numeric', 'visibility'];""")
s=s.replace("'EX2 s'","'EX6 s'").replace("'EX2 ERR '","'EX6 ERR '")
s=s.replace("MEAS = 15000","MEAS = 12000")
open('exp6-script.js','w').write(s)
PY
node --check exp6-script.js && node -e "
const fs=require('fs');let s=fs.readFileSync('exp6-script.js','utf8');
s=s.replace('WARM = 40000, SETTLE = 4000, MEAS = 12000','WARM = 2000, SETTLE = 300, MEAS = 900').replace('}, 3000);','}, 400);');
const {chromium}=require('playwright-core');(async()=>{
const b=await chromium.launch({executablePath:'/home/tjwise/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080}});
await p.goto('http://<mirror>:8080/',{waitUntil:'load'});
await p.evaluate(s);
for(let i=0;i<40;i++){await p.waitForTimeout(1000);const t=await p.title();if(t.includes('st=done')){console.log(t);break;}}
await b.close();})()" 2>&1 | tail -2


# --- L206  2026-09-22T01:29:08.724Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlPath="$HOME/.ssh/kiosk-%C" exp6-script.js root@<prod>:/home/root/.surf/script.js && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
systemctl restart kiosk
sleep 25
export DISPLAY=:0
XP=$(ps w | awk '/X :0 vt1/ && !/awk/ {print $1; exit}')
WK=$(ps w | awk '/WebKitWebProcess/ && !/awk/ {print $1; exit}')
echo "pids X=$XP WK=$WK"
i=0
while [ $i -lt 24 ]; do
  L=$(cut -d' ' -f1 /proc/loadavg)
  XC=$(awk '{print $14+$15}' /proc/$XP/stat)
  WC=$(awk '{print $14+$15}' /proc/$WK/stat)
  T=$(xprop -id 0x600002 WM_NAME | cut -c1-48)
  echo "$(date +%s) load=$L X=$XC WK=$WC $T"
  i=$((i+1)); sleep 8
done
echo "=== FINAL ==="
xprop -id 0x600002 WM_NAME
EOF


# --- L210  2026-09-22T01:33:43.984Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
: > /home/root/.surf/script.js
rm -rf /home/root/.surf/cache
wc -c /home/root/.surf/script.js
systemctl restart kiosk
sleep 45
echo "--- unit"; systemctl is-active kiosk; systemctl show kiosk -p NRestarts
echo "--- conf"; od -c /data/config/kiosk.conf | tail -8
echo "--- env in renderer (anchored exact match)"
WK=$(ps w | awk '/WebKitWebProcess/ && !/awk/ {print $1; exit}')
SF=$(ps w | awk '/surf -K/ && !/awk/ {print $1; exit}')
echo "surf=$SF webkit=$WK"
for p in $SF $WK; do echo -n "pid $p DMABUF="; tr '\0' '\n' < /proc/$p/environ | grep -c '^WEBKIT_DISABLE_DMABUF_RENDERER=1$'; done
echo "--- script.js + cache"; ls -la /home/root/.surf/; wc -c /home/root/.surf/script.js
echo "--- page state via title"; export DISPLAY=:0; xprop -id 0x600002 WM_NAME
echo "--- orphan loops"; ps w | grep -E 'decay|probe|rafpoll|\.sh' | grep -v grep
echo "--- load"; cat /proc/loadavg
EOF


# --- L213  2026-09-22T01:34:41.284Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && /home/tjwise/meta-wisekiosk/tools/kiosk-screenshot.sh root@<prod> final-clean.png 2>&1 | tail -4; echo "--- render check"; /home/tjwise/meta-wisekiosk/tools/kiosk-render-check.sh root@<prod> 900x400+500+300 2>&1 | tail -8


# --- L216  2026-09-22T01:35:39.439Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 -c "
from PIL import Image
im=Image.open('final-clean.png'); im.thumbnail((900,900)); im.save('final-clean-small.jpg',quality=80)
print(im.size)"; /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'date +%H:%M:%S'


# --- L218  2026-09-22T01:35:44.818Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && (command -v convert magick ffmpeg || true) && convert final-clean.png -resize 900x final-clean-small.jpg 2>&1 | tail -2; ls -la final-clean-small.jpg


# --- L227  2026-09-22T01:38:34.462Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && ls -la device-fix-test.md && command grep -c 'observation' device-fix-test.md && echo "--- final board recheck ---" && /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
wc -c /home/root/.surf/script.js; systemctl is-active kiosk; cat /proc/loadavg
export DISPLAY=:0; xprop -id 0x600002 WM_NAME
ps w | grep -E 'decay|probe|rafpoll' | grep -v grep; echo "orphan-check-done"
EOF
