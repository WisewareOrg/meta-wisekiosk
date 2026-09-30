#!/bin/sh
# Run 7 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: subagent agent-a2dc2d649d77c30fd.jsonl (lines 1-306)
# Timestamps: 2026-09-22T (see per-command timestamps)
# Commands are exactly as typed (full ordered sequence from the source subagent, minus
# nothing -- see MANIFEST.md for any run-boundary or exclusion notes).
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH. exp7 then exp8 (derived from exp7 by the transcript's own patch), each a single
# deploy-and-read pass, no retries found.



# --- L8  2026-09-22T01:47:43.234Z ---
ls /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/ 2>/dev/null


# --- L10  2026-09-22T01:47:43.895Z ---
cat /home/tjwise/WiseKiosk/frontend/src/modules/clock/Clock.svelte


# --- L13  2026-09-22T01:47:57.042Z ---
cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/device-fix-test.md


# --- L15  2026-09-22T01:47:58.028Z ---
cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/framerate-settle.md


# --- L19  2026-09-22T01:48:06.244Z ---
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' 2>&1 | head -20; echo "---"; curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:8080/ 2>&1; echo "---"; curl -sS http://localhost:8080/ 2>&1 | head -30


# --- L20  2026-09-22T01:48:07.602Z ---
cd /home/tjwise/WiseKiosk && git status --short 2>&1 | head -20; echo "--- branch:"; git branch --show-current; echo "--- compose.dev:"; cat compose.dev.yaml 2>/dev/null | head -40


# --- L25  2026-09-22T01:48:28.417Z ---
cd /home/tjwise/WiseKiosk && echo "=== file mtimes:"; ls -l --time-style=+%Y-%m-%d_%H:%M:%S frontend/src/app.css frontend/src/modules/park_wait_times/*.svelte frontend/src/modules/clock/Clock.svelte 2>&1; echo "=== container/image created:"; docker inspect wisekiosk-kiosk-1 --format '{{.Created}} image={{.Image}}' 2>&1; docker image inspect $(docker inspect wisekiosk-kiosk-1 --format '{{.Image}}') --format 'imgcreated={{.Created}}' 2>&1; echo "=== now:"; date +%Y-%m-%d_%H:%M:%S


# --- L31  2026-09-22T01:48:45.788Z ---
cd /home/tjwise/WiseKiosk && ls node_modules/.bin/ 2>/dev/null | grep -i -E 'playwright|vite' ; echo "--- global pw:"; which playwright npx node 2>&1; node -e "try{console.log('pw:',require.resolve('playwright'))}catch(e){console.log('no playwright in WiseKiosk')}" 2>&1


# --- L36  2026-09-22T01:49:07.944Z ---
ls /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/node_modules/.bin/ 2>&1 | head; echo "=== pkg:"; cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/package.json 2>&1; echo "=== chrome bins:"; ls ~/.cache/ms-playwright/ 2>&1; which chromium chromium-browser google-chrome 2>&1


# --- L42  2026-09-22T01:50:11.031Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-diag.mjs base 2>&1 | tail -60


# --- L50  2026-09-22T01:51:28.787Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-diag2.mjs base 2>&1 | tail -60


# --- L54  2026-09-22T01:52:14.452Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node -e "
const r=require('./sf2-base.json');
console.log('ancestor chain from .seconds upward:');
for(const c of r.landed.chain) console.log('  '+c.sel.padEnd(52)+' display='+c.display.padEnd(12)+' width='+String(c.widthSpec).padEnd(10)+' box='+c.w+'x'+c.h+' contain='+c.contain);
"


# --- L58  2026-09-22T01:52:33.194Z ---
cd /home/tjwise/WiseKiosk && grep -n -A14 '\.frame' frontend/src/lib/RegionFrame.svelte 2>/dev/null | head -50; echo "=== region:"; grep -n -B2 -A14 '\.region' frontend/src/lib/RegionFrame.svelte 2>/dev/null | head -40


# --- L63  2026-09-22T01:53:05.293Z ---
cd /home/tjwise/WiseKiosk && grep -rn 'FRAME_COLUMNS\|FRAME_ROWS' frontend/src/ | head


# --- L65  2026-09-22T01:53:06.673Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-ab.mjs base 2>&1 | tail -50


# --- L69  2026-09-22T01:54:54.083Z ---
cd /home/tjwise/WiseKiosk && echo "=== public/config.json clock:"; python3 -c "
import json;d=json.load(open('frontend/public/config.json'))
for m in d.get('modules',[]):
    if m.get('module')=='clock': print(json.dumps(m,indent=2))
" 2>&1; echo "=== type-annotation:"; grep -n 'type-annotation\|type-display\b' frontend/src/app.css | head


# --- L77  2026-09-22T01:55:35.763Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-sweep.mjs 2>&1 | tail -30


# --- L78  2026-09-22T01:55:37.709Z ---
cd /home/tjwise/WiseKiosk && echo "=== untracked deploy/config.json:"; head -60 deploy/config.json 2>&1; echo; echo "=== fixture/mock/cached flags in frontend src:"; grep -rn -i -E 'fixture|mock|msw|cached|offline|sample_data|demo' frontend/src --include=*.ts --include=*.svelte -l 2>/dev/null | head -20


# --- L83  2026-09-22T01:56:33.745Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-ab.mjs sizepx '{"contain":"size layout","width":"53px","height":"34.5625px"}' 2>&1 | tail -32


# --- L84  2026-09-22T01:56:36.781Z ---
cd /home/tjwise/WiseKiosk && echo "=== fixture-ish files:"; grep -rn -i -E 'fixture|mock|cached|offline|stale' frontend/src --include='*.ts' --include='*.svelte' -l 2>/dev/null | head -20; echo "=== backend cache:"; ls backend/ 2>/dev/null | head -20; grep -rn -i -E 'cache|fixture' backend/ --include='*.go' --include='*.py' --include='*.ts' -l 2>/dev/null | head -10; echo "=== Dockerfile srv:"; grep -n -i -E 'config.json|COPY|srv' Dockerfile 2>&1 | head -20


# --- L89  2026-09-22T01:57:38.104Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node -e "
const r=require('./sfab-sizepx.json');
console.log('landed before:',JSON.stringify(r.landed.before));
console.log('landed after :',JSON.stringify(r.landed.after));
console.log('seconds geom :',JSON.stringify(r.landed.geom.seconds));
"


# --- L91  2026-09-22T01:57:39.936Z ---
cd /home/tjwise/WiseKiosk && echo "=== cache.go head:"; head -50 backend/internal/cache/cache.go 2>&1; echo "=== env/flags in cmd:"; grep -rn -E 'flag\.|getenv|Getenv' backend/cmd/ backend/internal/router/router.go 2>/dev/null | head -25


# --- L97  2026-09-22T01:58:26.762Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-isolate.mjs 2>&1 | tail -20


# --- L105  2026-09-22T02:00:03.049Z ---
cd /home/tjwise/WiseKiosk && echo "=== frontend API calls:"; grep -rn -E "fetch\(|'/api|\"/api|api/" frontend/src --include='*.ts' --include='*.svelte' 2>/dev/null | grep -v test | grep -v spec | head -20; echo; echo "=== spec mock setup (park):"; sed -n '1,60p' frontend/src/modules/park_wait_times/park_wait_times.spec.ts 2>&1


# --- L108  2026-09-22T02:00:14.563Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && curl -sS -X POST http://localhost:8080/api/park-wait-times -H 'content-type: application/json' -d '{"parks":["magic-kingdom","epcot","universal-studios","hollywood-studios","animal-kingdom","islands-of-adventure"]}' -o pwt-live.json -w 'http=%{http_code} bytes=%{size_download}\n' 2>&1; python3 -c "
import json;d=json.load(open('pwt-live.json'))
for p in d.get('parks',[]):
    rides=p.get('rides') or []
    print(f\"{p.get('name')!r:45} available={p.get('available')} rides={len(rides)}\")
" 2>&1


# --- L112  2026-09-22T02:00:22.936Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 -c "
import json
d=json.load(open('pwt-live.json'))
epcot=[p for p in d['parks'] if p.get('available')][0]
print('epcot sample ride:', json.dumps(epcot['rides'][0]))
print('epcot keys:', list(epcot.keys()))
" 2>&1; echo "=== weather:"; curl -sS -X POST http://localhost:8080/api/weather -H 'content-type: application/json' -d '{"location":{"lat":29.2108,"lon":-81.0228}}' -o wx-live.json -w 'http=%{http_code} bytes=%{size_download}\n' 2>&1; head -c 300 wx-live.json; echo


# --- L115  2026-09-22T02:00:34.450Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 -c "
import json
live=json.load(open('pwt-live.json'))
epcot=[p for p in live['parks'] if p.get('available')][0]
names=['Magic Kingdom','Epcot','Universal Studios','Hollywood Studios','Animal Kingdom','Islands of Adventure']
rides=epcot['rides']
parks=[]
for i,n in enumerate(names):
    rs=[]
    for j,r in enumerate(rides):
        rs.append({'name': r['name'], 'state':'Operating', 'waitMinutes': 5+((i*7+j*5)%110)})
    parks.append({'available':True,'hours':epcot.get('hours'),'name':n,'rides':rs})
json.dump({'parks':parks}, open('pwt-fixture.json','w'), indent=1)
print('wrote pwt-fixture.json: parks=%d rides/park=%d' % (len(parks), len(parks[0]['rides'])))
print('hours sample:', json.dumps(epcot.get('hours'))[:160])
"


# --- L118  2026-09-22T02:00:49.934Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 -c "
import json,datetime
d=json.load(open('pwt-fixture.json'))
today=datetime.date.today().isoformat()
for p in d['parks']:
    p['hours']={'open': today+'T08:00:00-04:00','close': today+'T23:59:00-04:00'}
json.dump(d, open('pwt-fixture.json','w'), indent=1)
print('hours widened to', d['parks'][0]['hours'])
"; python3 - <<'EOF'
import re,pathlib
p=pathlib.Path('/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/sf-isolate.mjs')
s=p.read_text()
old="const browser = await chromium.launch"
new="""// Stable page: answer the park route from a frozen full-park fixture built from the live
// response's own shape. Parks close through the evening, which would otherwise change the DOM
// mid-run. Nothing on the device or the mirror is touched by this -- it is a client-side route
// intercept in this browser only.
const FIXTURE = JSON.parse(readFileSync(`${DIR}/pwt-fixture.json`, 'utf8'));

const browser = await chromium.launch"""
assert old in s
s=s.replace(old,new,1)
s=s.replace("import { writeFileSync } from 'node:fs';","import { writeFileSync, readFileSync } from 'node:fs';",1)
old2="await page.goto(URL, { waitUntil: 'networkidle' });"
new2="""await page.route('**/api/park-wait-times', (route) =>
  route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FIXTURE) }));
await page.goto(URL, { waitUntil: 'networkidle' });"""
assert old2 in s
s=s.replace(old2,new2,1)
# report the rendered card/ride count so the fixture is provably in effect
s=s.replace("const phases = await page.evaluate(async (N) => {",
 "const domBefore = await page.evaluate(() => ({ cards: document.querySelectorAll('.card').length, waits: document.querySelectorAll('.wait').length }));\nconst phases = await page.evaluate(async (N) => {",1)
s=s.replace("writeFileSync(`${DIR}/sf-isolate.json`, JSON.stringify({ N, phases, summary }, null, 2));",
 "const domAfter = await page.evaluate(() => ({ cards: document.querySelectorAll('.card').length, waits: document.querySelectorAll('.wait').length }));\nwriteFileSync(`${DIR}/sf-isolate.json`, JSON.stringify({ N, domBefore, domAfter, phases, summary }, null, 2));\nconsole.log('DOM cards/waits before:', JSON.stringify(domBefore), ' after:', JSON.stringify(domAfter));",1)
p.write_text(s)
print("patched sf-isolate.mjs")
EOF


# --- L120  2026-09-22T02:00:56.805Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-isolate.mjs 2>&1 | tail -14


# --- L126  2026-09-22T02:01:31.918Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-visual.mjs 2>&1 | tail -20; echo "=== pixel diff:"; python3 -c "
from PIL import Image, ImageChops
import sys
a=Image.open('sfv-before.png').convert('RGB'); b=Image.open('sfv-after.png').convert('RGB')
print('sizes:', a.size, b.size)
if a.size!=b.size: print('SIZE DIFFERS'); sys.exit()
d=ImageChops.difference(a,b); bb=d.getbbox()
px=sum(1 for p in d.getdata() if p!=(0,0,0))
print('differing pixels:', px, 'of', a.size[0]*a.size[1], ' bbox:', bb)
print('max channel delta:', max(max(p) for p in d.getdata()))
" 2>&1


# --- L130  2026-09-22T02:01:50.615Z ---
which compare magick convert identify ffmpeg 2>&1; python3 -c "import numpy; print('numpy ok', numpy.__version__)" 2>&1; node -e "console.log(require.resolve('pngjs'))" 2>&1 | head -2


# --- L132  2026-09-22T02:01:58.472Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && identify sfv-before.png sfv-after.png 2>&1; echo "=== AE (differing pixel count):"; compare -metric AE sfv-before.png sfv-after.png sfv-diff.png 2>&1; echo; echo "=== max abs difference:"; magick sfv-before.png sfv-after.png -compose difference -composite -format '%[fx:maxima*255]\n' info: 2>&1


# --- L136  2026-09-22T02:02:07.792Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && magick sfv-before.png sfv-after.png -compose difference -composite -threshold 5% -format 'diff bbox: %@\n' info: 2>&1; echo "=== crop that area from both, 4x zoom:"; magick sfv-before.png -crop 90x60+480+0 +repage -scale 400% sfv-z-before.png 2>&1; magick sfv-after.png -crop 90x60+480+0 +repage -scale 400% sfv-z-after.png 2>&1; magick sfv-z-before.png sfv-z-after.png +append sfv-zoom.png 2>&1; identify sfv-zoom.png


# --- L142  2026-09-22T02:03:10.258Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-variants.mjs 2>&1 | tail -12; echo; echo "=== pixel diff vs BASE:"; for v in V1-abs-strict V2-abs-size-layout V3-abs-sizelayout-em V4-abs-nocontain; do printf '%-24s ' "$v"; ae=$(compare -metric AE sfvar-BASE.png sfvar-$v.png null: 2>&1); bb=$(magick sfvar-BASE.png sfvar-$v.png -compose difference -composite -threshold 5% -format '%@' info: 2>&1); echo "AE=$ae  bbox=$bb"; done


# --- L148  2026-09-22T02:04:13.081Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-visual2.mjs >/dev/null 2>&1; echo "exit=$?"; echo "--- stability control (must be 0):"; compare -metric AE sfv2-stability-a.png sfv2-stability-b.png null: 2>&1; echo; for v in V1-abs-strict V2-abs-size-layout; do printf '%-22s ' "$v"; ae=$(compare -metric AE sfv2-$v-base.png sfv2-$v-fix.png null: 2>&1); bb=$(magick sfv2-$v-base.png sfv2-$v-fix.png -compose difference -composite -threshold 5% -format '%@' info: 2>&1); echo "AE=$ae bbox=$bb"; done


# --- L151  2026-09-22T02:04:44.813Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && echo "stability diff bbox:"; magick sfv2-stability-a.png sfv2-stability-b.png -compose difference -composite -threshold 5% -format '%@\n' info: 2>&1; echo "--- crop both at that area to see what moved:"; magick sfv2-stability-a.png -crop 560x60+490+80 +repage -scale 200% st-a.png; magick sfv2-stability-b.png -crop 560x60+490+80 +repage -scale 200% st-b.png; magick st-a.png st-b.png -append st-cmp.png; identify st-cmp.png


# --- L158  2026-09-22T02:05:28.934Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'EOF'
import pathlib
p=pathlib.Path('sf-visual2.mjs')
s=p.read_text()
# tight crop on the annotations column only (seconds + meridiem); the .clock rect is
# 1152px wide and overlaps the marquee, so it is not a valid visual-regression crop.
s=s.replace("page.locator('.clock').screenshot","page.locator('.annotations').screenshot")
# noise floor: three consecutive baseline shots before any variant
s=s.replace("""const shots = { stability: ['sfv2-stability-a.png', 'sfv2-stability-b.png'] };""",
"""await page.waitForTimeout(2500);
await page.locator('.annotations').screenshot({ path: `${DIR}/sfv2-stability-c.png` });
const shots = { stability: ['sfv2-stability-a.png', 'sfv2-stability-b.png', 'sfv2-stability-c.png'] };""")
p.write_text(s)
print('patched to crop .annotations + 3 stability shots')
EOF
node sf-visual2.mjs >/dev/null 2>&1; echo "exit=$?"
echo "--- crop size:"; identify sfv2-stability-a.png
echo "--- NOISE FLOOR (same state, shots 2.5s apart):"
printf '  a vs b: '; compare -metric AE sfv2-stability-a.png sfv2-stability-b.png null: 2>&1; echo
printf '  a vs c: '; compare -metric AE sfv2-stability-a.png sfv2-stability-c.png null: 2>&1; echo
echo "--- VARIANTS (vs their own adjacent baseline):"
for v in V1-abs-strict V2-abs-size-layout; do printf '  %-20s ' "$v"; ae=$(compare -metric AE sfv2-$v-base.png sfv2-$v-fix.png null: 2>&1); bb=$(magick sfv2-$v-base.png sfv2-$v-fix.png -compose difference -composite -threshold 5% -format '%@' info: 2>&1); echo "AE=$ae bbox=$bb"; done


# --- L162  2026-09-22T02:06:25.908Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && sed -n '1,80p' exp6-script.js


# --- L164  2026-09-22T02:06:31.107Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && sed -n '80,200p' exp6-script.js; echo "=== rafpoll.sh:"; cat rafpoll.sh 2>&1 | head -40


# --- L174  2026-09-22T02:07:35.111Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-smoke.mjs 2>&1 | tail -25


# --- L178  2026-09-22T02:08:06.726Z ---
ls tools/kiosk-*.sh 2>&1; echo "=== identity file present:"; ls -l local/device-identity.md 2>&1 | sed 's/.*local/local/'; echo "=== roles (redacted):"; grep -i -E 'prod|bench|role' local/device-identity.md 2>/dev/null | sed -E 's/([0-9]{1,3}\.){3}[0-9]{1,3}/<addr>/g' | head -10


# --- L180  2026-09-22T02:08:13.394Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//'); echo "resolved prod (not printed)"; tools/kiosk-ssh.sh root@$PROD 'echo "--- script.js:"; wc -c /home/root/.surf/script.js; echo "--- kiosk:"; systemctl is-active kiosk; systemctl show kiosk -p NRestarts --value; echo "--- env:"; for p in $(pgrep -x surf) $(pgrep -x WebKitWebProcess); do echo -n "pid$p dmabuf="; tr "\0" "\n" < /proc/$p/environ | grep -c "^WEBKIT_DISABLE_DMABUF_RENDERER=1$"; done; echo "--- load:"; cat /proc/loadavg; echo "--- stray loops:"; ps w | grep -E "decay|sample|rafpoll" | grep -v grep | wc -l; echo "--- date:"; date'


# --- L184  2026-09-22T02:08:22.156Z ---
cat tools/kiosk-ssh.sh


# --- L188  2026-09-22T02:08:34.533Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@$PROD 'cat > /home/root/.surf/script.js' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/exp7-script.js
echo "--- verify bytes on device vs local:"
tools/kiosk-ssh.sh root@$PROD 'wc -c /home/root/.surf/script.js; md5sum /home/root/.surf/script.js'
md5sum /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/exp7-script.js


# --- L190  2026-09-22T02:08:39.979Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@$PROD 'rm -rf /home/root/.surf/cache && echo "cache removed"; ls -d /home/root/.surf/cache 2>&1; systemctl restart kiosk; echo "restart issued"; date'


# --- L194  2026-09-22T02:08:53.148Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@$PROD 'sleep 50; export DISPLAY=:0; ID=$(xwininfo -root -children 2>/dev/null | awk "/1920x1080/{print \$1; exit}"); echo "win=$ID"; xprop -id "$ID" WM_NAME 2>&1 | head -c 600; echo; echo "--- load:"; cat /proc/loadavg; date'


# --- L196  2026-09-22T02:09:48.250Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@$PROD 'export DISPLAY=:0; xprop -id 0x600002 WM_NAME 2>&1 | cut -c1-500'


# --- L200  2026-09-22T02:10:07.143Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@$PROD 'export DISPLAY=:0
i=0
while [ $i -lt 20 ]; do
  T=$(xprop -id 0x600002 WM_NAME 2>/dev/null)
  case "$T" in *st=done*) echo "DONE"; echo "$T"; exit 0;; esac
  i=$((i+1)); sleep 15
done
echo "TIMEOUT"; xprop -id 0x600002 WM_NAME 2>/dev/null'


# --- L204  2026-09-22T02:12:59.991Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && cat > run1.txt <<'EOF'
b0|44|85|30|545|843|6.8|21|546|CONTENTCHANGED|static,none,block>static,none,block:inl0/1:chg0
F1|61|319|18|61|488|26.3|4|87|CONTENTCHANGED|static,none,block>absolute,size_layout,block:inl1/1:chg1
b1|77|96|22|430|597|7.9|6|475|CONTENTCHANGED|static,none,block>static,none,block:inl0/1:chg0
F2|93|288|20|67|492|23.9|6|97|CONTENTCHANGED|static,none,block>absolute,strict,block:inl1/1:chg1
b2|109|92|25|471|837|7.6|3|491|CONTENTCHANGED|static,none,block>static,none,block:inl0/1:chg0
C1|125|241|23|75|643|20.0|7|132|CONTENTCHANGED|static,none,block>static,none,none:inl1/1:chg1
b3|142|75|48|532|809|6.2|16|452|CONTENTCHANGED|static,none,block>static,none,block:inl0/1:chg0
F1b|158|334|20|59|418|27.8|5|85|CONTENTCHANGED|static,none,block>absolute,size_layout,block:inl1/1:chg1
b4|174|66|50|567|713|5.4|17|537|CONTENTCHANGED|static,none,block>static,none,block:inl0/1:chg0
EOF
awk -F'|' 'BEGIN{printf "%-5s %-6s %-8s %-9s %-8s %-10s %s\n","ph","fps","med(ms)","p90(ms)","lateMed","lateP90","landed"}
{printf "%-5s %-6s %-8s %-9s %-8s %-10s %s\n",$1,$7,$4,$5,$8,$9,($11 ~ /chg1/ ? "YES" : "-")}' run1.txt
echo
echo "baseline band (fps): $(awk -F'|' '$1 ~ /^b/{printf "%s ",$7}' run1.txt)"
echo "baseline p90 (ms)  : $(awk -F'|' '$1 ~ /^b/{printf "%s ",$5}' run1.txt)"
echo "fix p90 (ms)       : $(awk -F'|' '$1 ~ /^F/{printf "%s ",$5}' run1.txt)"
echo "control p90 (ms)   : $(awk -F'|' '$1 ~ /^C/{printf "%s ",$5}' run1.txt)"


# --- L208  2026-09-22T02:13:21.080Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'EOF'
import pathlib
s=pathlib.Path('exp7-script.js').read_text()
s=s.replace('var WARM = 40000, SETTLE = 4000, MEAS = 12000;','var WARM = 40000, SETTLE = 4000, MEAS = 30000;')
s=s.replace("'EX7","'EX8")
s=s.replace("document.title = 'EX7 ERR","document.title = 'EX8 ERR")
# structural-only content guard: wait TEXT rotates as a matter of course, so keying on it
# flags every window. Card count and total element count change only when a park opens or
# closes, which is the confound worth excluding.
s=s.replace("""  function contentSig() {
    var w = q('.wait'), s = '', i;
    for (i = 0; i < w.length; i++) s += w[i].textContent + '|';
    return q('.card').length + ':' + w.length + ':' + s.length;
  }""",
"""  function contentSig() {
    return q('.card').length + ':' + q('.wait').length + ':' + document.querySelectorAll('*').length;
  }""")
# five phases, 30 s each
import re
start=s.index('  var PH = ['); end=s.index('  ];', start)+4
s = s[:start] + """  var PH = [
    { id: 'b0', el: [], par: [] },
    { id: 'F1', el: [['position','absolute'],['top','0px'],['left','0px'],['contain','size layout'],['width','53px'],['height','34.5625px']], par: [['position','relative']] },
    { id: 'b1', el: [], par: [] },
    { id: 'C1', el: [['display','none']], par: [] },
    { id: 'b2', el: [], par: [] }
  ];""" + s[end:]
pathlib.Path('exp8-script.js').write_text(s)
print('wrote exp8-script.js')
EOF
sed -i "s/exp7-script.js/exp8-script.js/; s/'b0', 'F1', 'b1', 'F2', 'b2', 'C1', 'b3', 'F1b', 'b4'/'b0', 'F1', 'b1', 'C1', 'b2'/; s/\['F1', 'F2', 'C1', 'F1b'\]/['F1','C1']/; s/\['b0', 'b1', 'b2', 'b3', 'b4'\]/['b0','b1','b2']/; s/MEAS = 30000;'/MEAS = 1400;'/" sf-smoke.mjs
sed -i "s/var WARM = 40000, SETTLE = 4000, MEAS = 12000;'/var WARM = 40000, SETTLE = 4000, MEAS = 30000;'/" sf-smoke.mjs
grep -n "replace('var WARM" sf-smoke.mjs
node sf-smoke.mjs 2>&1 | tail -12


# --- L211  2026-09-22T02:13:41.907Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
S=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
tools/kiosk-ssh.sh root@$PROD 'cat > /home/root/.surf/script.js' < $S/exp8-script.js
tools/kiosk-ssh.sh root@$PROD 'md5sum /home/root/.surf/script.js'; md5sum $S/exp8-script.js
tools/kiosk-ssh.sh root@$PROD 'rm -rf /home/root/.surf/cache; systemctl restart kiosk; date'


# --- L213  2026-09-22T02:13:49.907Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@$PROD 'export DISPLAY=:0
i=0
while [ $i -lt 26 ]; do
  T=$(xprop -id 0x600002 WM_NAME 2>/dev/null)
  case "$T" in *st=done*) echo "DONE"; echo "$T"; exit 0;; esac
  i=$((i+1)); sleep 15
done
echo "TIMEOUT"; xprop -id 0x600002 WM_NAME 2>/dev/null' > /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/run2.txt 2>&1


# --- L223  2026-09-22T02:15:47.838Z ---
cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bphysw94g.output 2>/dev/null | tail -3; echo "=== build my edit to a temp dist (does not touch the mirror):"; cd /home/tjwise/WiseKiosk/frontend && npx vite build --outDir /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/dist-fix --emptyOutDir 2>&1 | tail -12


# --- L227  2026-09-22T02:16:01.607Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && echo "=== seconds rules in the built CSS:"; grep -o '\.seconds[a-z-]*\.svelte-[a-z0-9]*[^}]*}' dist-fix/assets/index-uRXasYzZ.css | head -8; echo; echo "=== containment present:"; grep -c 'contain:size layout\|contain: size layout' dist-fix/assets/index-uRXasYzZ.css


# --- L231  2026-09-22T02:16:33.485Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-verify-build.mjs 2>&1 | tail -25


# --- L237  2026-09-22T02:17:30.114Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && sed -i "s|await page.route('\*\*/api/\*\*', async (r) => {|await page.route('**/healthz', async (r) => {\n    const res = await fetch(MIRROR + '/healthz');\n    r.fulfill({ status: res.status, contentType: res.headers.get('content-type') ?? 'application/json', body: Buffer.from(await res.arrayBuffer()) });\n  });\n  await page.route('**/api/**', async (r) => {|" sf-verify-build.mjs && grep -n 'healthz' sf-verify-build.mjs
cd /home/tjwise/WiseKiosk/frontend && npx vite build --outDir /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/dist-fix --emptyOutDir 2>&1 | tail -2
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-verify-build.mjs 2>&1 | tail -20


# --- L241  2026-09-22T02:17:51.865Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && echo "=== pixel diff of the annotations column, real builds:"; identify sfb-base.png sfb-fix.png; printf 'AE='; compare -metric AE sfb-base.png sfb-fix.png null: 2>&1; echo; magick sfb-base.png sfb-fix.png -compose difference -composite -threshold 5% -format 'bbox=%@\n' info: 2>&1
echo; echo "=== RUN 2 (30 s windows):"; cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bphysw94g.output 2>/dev/null | tail -3


# --- L245  2026-09-22T02:18:00.758Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && echo "=== task output:"; cat tasks/bphysw94g.output 2>&1 | tail -5; echo "=== run2.txt:"; cat scratchpad/run2.txt 2>&1 | tail -5


# --- L249  2026-09-22T02:18:22.571Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@$PROD ': > /home/root/.surf/script.js; rm -rf /home/root/.surf/cache; systemctl restart kiosk; sleep 45; echo "=== script.js bytes:"; wc -c /home/root/.surf/script.js; echo "=== kiosk:"; systemctl is-active kiosk; echo -n "NRestarts="; systemctl show kiosk -p NRestarts --value; echo "=== dmabuf in surf + web process:"; for p in $(pgrep -x surf) $(pgrep -x WebKitWebProcess); do echo -n "pid$p="; tr "\0" "\n" < /proc/$p/environ | grep -c "^WEBKIT_DISABLE_DMABUF_RENDERER=1$"; done; echo "=== window title (must be plain):"; export DISPLAY=:0; xprop -id 0x600002 WM_NAME 2>&1 | cut -c1-200; echo "=== stray loops:"; ps w | grep -E "decay|sample|rafpoll|exp[0-9]" | grep -v grep | wc -l; echo "=== load:"; cat /proc/loadavg; date'


# --- L253  2026-09-22T02:19:18.869Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@$PROD 'echo "=== kiosk process tree:"; ps w | grep -E "surf|WebKit|xinit|Xorg|kiosk-launch" | grep -v grep; echo "=== dmabuf per pid (anchored exact match):"; for p in $(ls /proc | grep -E "^[0-9]+$"); do c=$(cat /proc/$p/comm 2>/dev/null); case "$c" in surf|WebKitWebProcess|WebKitNetworkP*) echo -n "$c($p)="; tr "\0" "\n" < /proc/$p/environ 2>/dev/null | grep -c "^WEBKIT_DISABLE_DMABUF_RENDERER=1$";; esac; done'


# --- L256  2026-09-22T02:19:34.982Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
tools/kiosk-ssh.sh root@$PROD 'for p in 29663 29691 29680; do echo -n "$(cat /proc/$p/comm)($p) dmabuf="; tr "\0" "\n" < /proc/$p/environ | grep -c "^WEBKIT_DISABLE_DMABUF_RENDERER=1$"; done' 2>&1
echo "=== screenshot + render check:"
tools/kiosk-screenshot.sh 2>&1 | tail -4
tools/kiosk-render-check.sh 2>&1 | tail -4


# --- L258  2026-09-22T02:19:41.865Z ---
PROD=$(grep -E '^prod\.address' local/device-identity.md | sed -E 's/.*=\s*//')
cd /home/tjwise/meta-wisekiosk
S=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad
tools/kiosk-screenshot.sh root@$PROD $S/final-panel.png 2>&1 | tail -4
echo "=== render advancing:"
tools/kiosk-render-check.sh root@$PROD 900x400+500+300 2>&1 | tail -4


# --- L260  2026-09-22T02:20:37.046Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && magick final-panel.png -crop 1200x300+60+80 +repage -resize 70% final-clock-crop.png && identify final-clock-crop.png


# --- L266  2026-09-22T02:20:48.585Z ---
cd /home/tjwise/WiseKiosk && grep -n 'seconds' frontend/src/modules/clock/clock.spec.ts | head -20; echo "=== other refs to .seconds in tree:"; grep -rn "seconds'" frontend/src frontend/tests 2>/dev/null | grep -v node_modules | grep -iE "queryselector|locator|getby|css|class" | head -10


# --- L270  2026-09-22T02:20:58.969Z ---
cd /home/tjwise/WiseKiosk/frontend && python3 -c "
import json;d=json.load(open('package.json'));print(json.dumps(d.get('scripts'),indent=1))"


# --- L272  2026-09-22T02:21:04.028Z ---
cd /home/tjwise/WiseKiosk && ls package.json justfile Makefile 2>&1; python3 -c "
import json;d=json.load(open('package.json'));print(json.dumps(d.get('scripts'),indent=1))" 2>&1 | head -20; echo "=== justfile test recipes:"; grep -n -E '^[a-z-]+.*:' justfile 2>/dev/null | grep -i -E 'test|check|verify|spec' | head


# --- L274  2026-09-22T02:21:10.302Z ---
cd /home/tjwise/WiseKiosk && grep -n -i -E 'playwright|vitest|spec|frontend-test|render' justfile | head -20


# --- L276  2026-09-22T02:21:15.346Z ---
cd /home/tjwise/WiseKiosk && timeout 600 frontend/node_modules/.bin/playwright test --config frontend/playwright.config.ts clock 2>&1 | tail -30


# --- L284  2026-09-22T02:22:19.629Z ---
cd /home/tjwise/WiseKiosk/frontend && npx vite build --outDir /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/dist-fix --emptyOutDir 2>&1 | tail -2
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && sed -i "s/'.seconds-gauge', //" sf-verify-build.mjs && node sf-verify-build.mjs 2>&1 | tail -18


# --- L287  2026-09-22T02:22:35.350Z ---
cd /home/tjwise/WiseKiosk && timeout 900 frontend/node_modules/.bin/playwright test --config frontend/playwright.config.ts clock 2>&1 | tail -12


# --- L291  2026-09-22T02:23:02.660Z ---
cd /home/tjwise/WiseKiosk && timeout 300 frontend/node_modules/.bin/vitest run --root frontend clock 2>&1 | tail -8; echo "=== DIFF ==="; git diff -- frontend/src/modules/clock/Clock.svelte


# --- L297  2026-09-22T02:23:29.626Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 - <<'EOF'
import json, pathlib
cfg=json.load(open('/home/tjwise/WiseKiosk/frontend/public/config.json'))
for m in cfg['modules']:
    if m['module']=='clock':
        m['options']['twenty_four_hour']=True   # no meridiem: the column is the slot alone
pathlib.Path('config-24h.json').write_text(json.dumps(cfg))
print('wrote config-24h.json (twenty_four_hour=true, show_seconds=true)')
EOF
sed -i "s|await page.route('\*\*/api/park-wait-times'|await page.route('**/config.json', (r) =>\n    r.fulfill({ status: 200, contentType: 'application/json', body: readFileSync(\`\${DIR}/config-24h.json\`,'utf8') }));\n  await page.route('**/api/park-wait-times'|" sf-verify-build.mjs
grep -n 'config-24h' sf-verify-build.mjs
cd /home/tjwise/WiseKiosk/frontend && npx vite build --outDir /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/dist-fix --emptyOutDir 2>&1 | tail -1
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && node sf-verify-build.mjs 2>&1 | tail -16


# --- L304  2026-09-22T02:25:47.492Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && echo "=== identity leak check in deliverable:"; command grep -nEc '([0-9]{1,3}\.){3}[0-9]{1,3}|raspberrypi|<bench-hostname>|([0-9a-f]{2}:){5}' seconds-fix.md; echo "(0 = clean)"; echo "=== wc:"; wc -l seconds-fix.md
echo "=== final source state:"; cd /home/tjwise/WiseKiosk && git status --short frontend/src/modules/clock/ && git diff --stat -- frontend/src/modules/clock/Clock.svelte
