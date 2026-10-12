#!/bin/bash
set -u
BACKUP=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/kiosk.conf.orig5
AFTER=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/kiosk.conf.restored5
KSSH=/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-ssh.sh

echo "--- opening tunnel ---"
ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 \
  -L 2999:127.0.0.1:2999 -N 'root@<BENCH_ADDRESS>' &
TUNNEL_PID=$!
sleep 3

echo "--- querying WebGL renderer ---"
JS='(function(){var c=document.createElement("canvas");var gl=c.getContext("webgl")||c.getContext("experimental-webgl");if(!gl)return "NO_WEBGL_CONTEXT";var d=gl.getExtension("WEBGL_debug_renderer_info");if(d){return "UNMASKED_RENDERER="+gl.getParameter(d.UNMASKED_RENDERER_WEBGL)+" | UNMASKED_VENDOR="+gl.getParameter(d.UNMASKED_VENDOR_WEBGL);}return "RENDERER="+gl.getParameter(gl.RENDERER)+" | VENDOR="+gl.getParameter(gl.VENDOR);})()'
node /home/tjwise/meta-wisekiosk/.claude/skills/webkit-inspector/webkit-inspect.mjs eval "$JS"
RC=$?
echo "eval_rc=$RC"

echo "--- closing tunnel ---"
kill "$TUNNEL_PID" 2>/dev/null
wait "$TUNNEL_PID" 2>/dev/null

echo "--- restoring kiosk.conf ---"
"$KSSH" 'root@<BENCH_ADDRESS>' 'cat > /data/config/kiosk.conf' < "$BACKUP"
"$KSSH" 'root@<BENCH_ADDRESS>' 'systemctl restart kiosk'
sleep 5
"$KSSH" 'root@<BENCH_ADDRESS>' 'cat /data/config/kiosk.conf' > "$AFTER"
cmp "$BACKUP" "$AFTER" && echo RESTORE_IDENTICAL || echo RESTORE_MISMATCH
"$KSSH" 'root@<BENCH_ADDRESS>' 'journalctl -u kiosk -b --no-pager | tail -4'
