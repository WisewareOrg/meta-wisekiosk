#!/bin/sh
# Runs 3 and 4 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: subagent agent-a773faf4212624f5d.jsonl (lines 1-369)
# Timestamps: 2026-09-22T19:06:20Z - 2026-09-22T19:50:22Z
# Commands are exactly as typed (full ordered sequence from the source subagent, minus
# nothing -- see MANIFEST.md for any run-boundary or exclusion notes).
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH on the commands themselves (single continuous session, no retries found) and on
# their numbers matching the README's Run 3/4 prose. MEDIUM on the Run 3/Run 4 split specifically:
# Run 4 continues inside this same session by continuity (no redeploy, no restart -- the README's
# own basis statement), and no command marks where Run 3's reading ends and Run 4's begins, so this
# file carries the full ordered sequence for both rather than an invented split point. Included
# rather than trimmed: a remote-inspector sub-thread (~lines 224-297, 2026-09-21T19:29:15Z-
# 19:34:56Z) that produced no cited number, left in because it sits between two commands that do
# belong to Run 3 (pause.js/blank.js) and could not be cleanly lifted out.


# --- L6  2026-09-21T19:06:20.738Z ---
ls /home/tjwise/meta-wisekiosk/tools/ && echo "---" && cat /home/tjwise/meta-wisekiosk/local/device-identity.md 2>/dev/null | head -40


# --- L8  2026-09-21T19:06:21.494Z ---
ls /home/tjwise/meta-wisekiosk/docs/issue_investigation/ 2>/dev/null


# --- L12  2026-09-21T19:06:25.051Z ---
ls /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing/ && echo "=== README head ===" && head -100 /home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing/README.md 2>/dev/null


# --- L14  2026-09-21T19:06:25.766Z ---
cat /home/tjwise/meta-wisekiosk/tools/kiosk-ssh.sh


# --- L18  2026-09-21T19:06:30.684Z ---
grep -n "vsync" -i docs/issue_investigation/gpu_compositing/README.md | head -30


# --- L20  2026-09-21T19:06:33.405Z ---
timeout 60 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== uptime/load ==="; uptime; cat /proc/loadavg
echo "=== buildinfo ==="; grep ^meta-wisekiosk /etc/buildinfo 2>/dev/null
echo "=== kiosk unit ==="; systemctl is-active kiosk xorg 2>/dev/null; systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null | head -20
echo "=== X processes ==="; ps w | grep -iE 'x|surf|kiosk' | grep -v grep
EOF


# --- L24  2026-09-21T19:06:50.352Z ---
timeout 120 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== CPU sample: top 2 iterations, 5s apart ==="
top -b -n 2 -d 5 2>&1 | tail -n 30
echo "=== /proc/loadavg ==="; cat /proc/loadavg
echo "=== meminfo key ==="; grep -E 'MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree|Cma' /proc/meminfo
echo "=== nr cpus ==="; grep -c ^processor /proc/cpuinfo
echo "=== Xorg log location ==="; ls -la /var/log/Xorg*.log* 2>&1; ls -la /root/.local/share/xorg/ 2>&1
EOF


# --- L28  2026-09-21T19:07:03.917Z ---
timeout 120 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== top (2 iters, 5s) head ==="
top -b -n 2 -d 5 2>&1 | head -n 40
EOF


# --- L30  2026-09-21T19:07:06.037Z ---
timeout 60 tools/kiosk-ssh.sh root@<prod> 'cat /var/log/Xorg.0.log' > /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/Xorg.0.log; echo "exit=$?"; wc -l /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/Xorg.0.log


# --- L38  2026-09-21T19:07:39.120Z ---
timeout 90 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== /etc/X11/xorg.conf ==="; cat /etc/X11/xorg.conf 2>&1
echo "=== xorg.conf.d ==="; ls -la /etc/X11/xorg.conf.d/ 2>&1; cat /etc/X11/xorg.conf.d/* 2>&1
echo "=== kiosk.conf ==="; cat /data/config/kiosk.conf 2>&1
echo "=== kiosk-launch ==="; cat /usr/bin/kiosk-launch 2>&1
EOF


# --- L40  2026-09-21T19:07:41.803Z ---
timeout 90 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== interrupts ==="; cat /proc/interrupts
echo "=== dri devices ==="; ls -la /dev/dri/ 2>&1
echo "=== debugfs mounted? ==="; mount | grep -i debug 2>&1
echo "=== dri debugfs ==="; ls /sys/kernel/debug/dri/ 2>&1; ls /sys/kernel/debug/dri/0/ 2>&1
echo "=== drm driver ==="; cat /sys/class/drm/card0/device/uevent 2>&1; ls /sys/class/drm/ 2>&1
EOF


# --- L44  2026-09-21T19:07:58.962Z ---
timeout 90 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== dri/0/state ==="; cat /sys/kernel/debug/dri/0/state 2>&1
echo "=== dri/0/framebuffer ==="; cat /sys/kernel/debug/dri/0/framebuffer 2>&1
echo "=== dri/0/clients ==="; cat /sys/kernel/debug/dri/0/clients 2>&1
echo "=== dri/0/name ==="; cat /sys/kernel/debug/dri/0/name 2>&1
EOF


# --- L48  2026-09-21T19:08:22.086Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
# --- Probe A: does plane-0's fb id ever change? (page-flip discriminator) ---
echo "=== A: plane-0 fb id, 40 rapid samples ==="
i=0
while [ $i -lt 40 ]; do
  U=$(cut -d' ' -f1 /proc/uptime)
  F=$(grep -m1 -o 'fb=[0-9]*' /sys/kernel/debug/dri/0/state)
  echo "$U $F"
  i=$((i+1))
done
echo "=== A2: X-allocated framebuffers now ==="
grep -B0 -A1 '^framebuffer' /sys/kernel/debug/dri/0/framebuffer | grep -E '^framebuffer|allocated'
EOF


# --- L52  2026-09-21T19:08:42.162Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
irq() { grep "$1" /proc/interrupts | tr -s ' ' | cut -d' ' -f3; }
pcpu() { awk '{print $14+$15}' /proc/$1/stat 2>/dev/null; }
XP=4714; SP=4718; WP=4746

echo "=== B: 20s window, IRQ + per-process CPU (USER_HZ=$(getconf CLK_TCK 2>/dev/null || echo 100)) ==="
V1=$(irq 'vc4 firmware kms'); G1=$(irq ' vc4$'); T1=$(cut -d' ' -f1 /proc/uptime)
X1=$(pcpu $XP); S1=$(pcpu $SP); W1=$(pcpu $WP)
I1=$(awk '/^cpu /{print $5}' /proc/stat); C1=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8}' /proc/stat)
sleep 20
V2=$(irq 'vc4 firmware kms'); G2=$(irq ' vc4$'); T2=$(cut -d' ' -f1 /proc/uptime)
X2=$(pcpu $XP); S2=$(pcpu $SP); W2=$(pcpu $WP)
I2=$(awk '/^cpu /{print $5}' /proc/stat); C2=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8}' /proc/stat)

echo "elapsed_s        = $(awk "BEGIN{printf \"%.2f\", $T2-$T1}")"
echo "vblank_irq_delta = $((V2-V1))   rate=$(awk "BEGIN{printf \"%.2f\", ($V2-$V1)/($T2-$T1)}") /s"
echo "v3d_irq_delta    = $((G2-G1))   rate=$(awk "BEGIN{printf \"%.2f\", ($G2-$G1)/($T2-$T1)}") /s"
echo "X_cpu_pct        = $(awk "BEGIN{printf \"%.1f\", ($X2-$X1)/($C2-$C1)*100}")"
echo "surf_cpu_pct     = $(awk "BEGIN{printf \"%.1f\", ($S2-$S1)/($C2-$C1)*100}")"
echo "webproc_cpu_pct  = $(awk "BEGIN{printf \"%.1f\", ($W2-$W1)/($C2-$C1)*100}")"
echo "idle_pct         = $(awk "BEGIN{printf \"%.1f\", ($I2-$I1)/($C2-$C1)*100}")"
echo "loadavg          = $(cat /proc/loadavg)"
EOF


# --- L56  2026-09-21T19:09:58.596Z ---
timeout 60 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== xrandr? ==="; which xrandr xdpyinfo xset 2>&1
echo "=== crtc-0 debugfs ==="; cat /sys/kernel/debug/dri/0/crtc-0 2>&1 | head -n 30
echo "=== modesetting TearFree support ==="; strings /usr/lib/xorg/modules/drivers/modesetting_drv.so 2>/dev/null | grep -iE '^TearFree$|^PageFlip$|^SWcursor$|^VariableRefresh$|^AsyncFlipSecondaries$|^Atomic$' 
echo "=== surf milestones tail ==="; tail -n 15 /var/log/surf-milestones.log 2>&1
EOF


# --- L57  2026-09-21T19:09:59.489Z ---
head -n 60 /home/tjwise/meta-wisekiosk/tools/kiosk-render-check.sh


# --- L62  2026-09-21T19:10:58.695Z ---
timeout 120 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== TearFree present in modesetting driver at all? ==="
strings /usr/lib/xorg/modules/drivers/modesetting_drv.so 2>/dev/null | grep -i tearfree | head -n 5
echo "(end tearfree grep; empty = option absent)"
echo "=== filesystem writability ==="
mount | grep -E ' / | /etc| /data'
echo "=== xrandr current ==="
DISPLAY=:0 xrandr 2>&1 | head -n 25
EOF


# --- L64  2026-09-21T19:11:02.772Z ---
timeout 120 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== WEBKIT_DEBUG channels available in this build (compositing/render related) ==="
for L in /usr/lib/libwebkit2gtk-4.1.so.0 /usr/lib/libwebkit2gtk-4.1.so; do
  [ -e "$L" ] && { echo "--- $L ---"; strings "$L" 2>/dev/null | grep -xE 'Compositing|Layers|AcceleratedCompositing|ThreadedCompositor|DisplayLink|Animations|Rendering|Screen|Events|Painting|WebGL|Media|Resize|Scrolling' | sort -u; break; }
done
echo "=== lib present? ==="; ls -la /usr/lib/libwebkit2gtk* 2>&1 | head -n 5
EOF


# --- L68  2026-09-21T19:11:31.359Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
L=/usr/lib/libwebkit2gtk-4.1.so.0.13.7
echo "=== is WEBKIT_DEBUG / logging compiled in? (binary grep, counts) ==="
for P in WEBKIT_DEBUG WEBKIT_LOG_LEVEL AcceleratedCompositing ThreadedCompositor LOG_CHANNEL initializeLogChannel WEBKIT_FORCE_VBLANK_TIMER; do
  printf '%-28s %s\n' "$P" "$(grep -a -c -- "$P" "$L" 2>/dev/null)"
done
echo "=== env var strings actually present (WEBKIT_*) ==="
grep -a -o -- 'WEBKIT_[A-Z_]*' "$L" 2>/dev/null | sort -u | head -n 40
EOF


# --- L74  2026-09-21T19:13:42.167Z ---
until [ -s /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b5hpa1jvi.output ] && grep -q 'WEBKIT_' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b5hpa1jvi.output 2>/dev/null; do sleep 10; done; echo READY


# --- L85  2026-09-21T19:14:07.812Z ---
timeout 60 tools/kiosk-ssh.sh root@<prod> 'killall grep 2>&1; echo "killed rc=$?"; ps w | grep -c "[g]rep"'


# --- L87  2026-09-21T19:14:12.971Z ---
timeout 60 tools/kiosk-ssh.sh root@<prod> 'killall grep; killall sh; ps w | grep "[g]rep\|libwebkit" | head -n 5; echo "---"; cut -d" " -f1 /proc/loadavg'


# --- L91  2026-09-21T19:14:33.394Z ---
timeout 60 tools/kiosk-ssh.sh root@<prod> 'killall grep; ps w | grep "[g]rep" | head -n 5; echo "--- load ---"; cat /proc/loadavg; echo "--- kiosk still up? ---"; systemctl is-active kiosk; ps w | grep -c "[s]urf -K"'


# --- L95  2026-09-21T19:14:45.273Z ---
timeout 900 tools/kiosk-ssh.sh root@<prod> 'grep -a -o -E "WEBKIT_[A-Z0-9_]{3,}" /usr/lib/libwebkit2gtk-4.1.so.0.13.7 | sort -u; echo "===GREP_DONE==="' 2>&1 | tee /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/webkit-envvars.txt


# --- L104  2026-09-21T19:15:50.738Z ---
until grep -q 'GREP_DONE' /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b27vu6n0t.output 2>/dev/null; do sleep 15; done; echo DONE


# --- L108  2026-09-21T19:15:55.293Z ---
grep -rn "FORCE_VBLANK\|VBLANK" --include=* . 2>/dev/null | grep -v '^\./\.git/' | head -30


# --- L110  2026-09-21T19:15:56.285Z ---
sed -n '200,260p' docs/issue_investigation/gpu_compositing/README.md


# --- L118  2026-09-21T19:17:04.636Z ---
timeout 60 tools/kiosk-ssh.sh root@<prod> 'killall grep; sleep 2; ps w | grep "[g]rep" | head -n 3; echo "--- settled load ---"; cat /proc/loadavg'


# --- L124  2026-09-21T19:17:12.992Z ---
cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b27vu6n0t.output


# --- L128  2026-09-21T19:17:44.652Z ---
timeout 90 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== kiosk.service ==="; systemctl cat kiosk 2>&1 | head -n 40
echo "=== surf environ (WEBKIT/KIOSK vars actually in the running process) ==="
tr '\0' '\n' < /proc/$(ps w | grep '[s]urf -K' | awk '{print $1}')/environ | grep -E 'WEBKIT|KIOSK|DISPLAY|GTK|SURF' | sort
echo "=== webprocess environ ==="
tr '\0' '\n' < /proc/$(ps w | grep '[W]ebKitWebProcess' | awk '{print $1}')/environ | grep -E 'WEBKIT|GTK' | sort
echo "=== gtk settings / xsettings present? (prefers-reduced-motion input) ==="
ls -la /etc/gtk-3.0/settings.ini /root/.config/gtk-3.0/settings.ini /home/root/.config/gtk-3.0/settings.ini 2>&1
ps w | grep -i '[x]settings\|[g]nome-settings' | head -n 3
echo "(no xsettings daemon line above = none running)"
EOF


# --- L132  2026-09-21T19:18:03.725Z ---
timeout 120 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
set -e
# Backup before any edit. Revert = cp this back + systemctl restart kiosk
if [ ! -f /data/config/kiosk.conf.bak-stutter ]; then
  cp -p /data/config/kiosk.conf /data/config/kiosk.conf.bak-stutter
  echo "backup created"
else
  echo "backup already exists (left alone)"
fi
echo "--- backup contents (line count only, contains site config) ---"
wc -l < /data/config/kiosk.conf.bak-stutter
# Write via temp + mv, never in place
cp /data/config/kiosk.conf /tmp/kiosk.conf.new
grep -q '^WEBKIT_SHOW_FPS=' /tmp/kiosk.conf.new || echo 'WEBKIT_SHOW_FPS=1' >> /tmp/kiosk.conf.new
mv /tmp/kiosk.conf.new /data/config/kiosk.conf
echo "--- keys now set (values redacted) ---"
cut -d= -f1 /data/config/kiosk.conf
EOF


# --- L136  2026-09-21T19:18:35.487Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== restarting kiosk ==="
systemctl restart kiosk
echo "restart issued rc=$?"
# verify by STATE, not exit code
n=0
while [ $n -lt 24 ]; do
  sleep 5
  A=$(systemctl is-active kiosk)
  S=$(ps w | grep -c '[s]urf -K')
  W=$(ps w | grep -c '[W]ebKitWebProcess')
  echo "t=$((n*5+5))s active=$A surf=$S webproc=$W"
  [ "$A" = "active" ] && [ "$S" -ge 1 ] && [ "$W" -ge 1 ] && break
  n=$((n+1))
done
EOF


# --- L140  2026-09-21T19:18:54.139Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
sleep 45
echo "=== env confirms SHOW_FPS reached web process ==="
tr '\0' '\n' < /proc/$(ps w | grep '[W]ebKitWebProcess' | awk '{print $1}')/environ | grep -E 'WEBKIT' | sort
echo "=== surf-milestones.log tail (FPS would land here via 2>&1|tee) ==="
tail -n 25 /var/log/surf-milestones.log
echo "=== journal for kiosk, last 40 lines ==="
journalctl -u kiosk --no-pager -n 40 2>&1 | tail -n 40
EOF


# --- L144  2026-09-21T19:20:04.772Z ---
sed -n '1,40p' /home/tjwise/meta-wisekiosk/tools/kiosk-screenshot.sh


# --- L146  2026-09-21T19:20:09.173Z ---
timeout 300 tools/kiosk-screenshot.sh root@<prod> /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/fps-check.png 2>&1 | tail -n 20


# --- L152  2026-09-21T19:20:48.757Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && magick fps-check.png -resize '1400x1400>' -quality 85 fps-small.jpg && magick fps-check.png -crop 600x200+0+0 +repage -resize 200% fps-corner.png && echo ok && ls -la fps-small.jpg fps-corner.png


# --- L158  2026-09-21T19:20:59.666Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && magick fps-check.png -crop 120x40+0+0 +repage -filter point -resize 700% fps-tiny.png && echo ok


# --- L164  2026-09-21T19:21:25.755Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && magick fps-check.png -crop 200x30+0+0 +repage -auto-level -filter point -resize 600% fps-enh.png && echo "--- pixel stats of corner region ---" && magick fps-check.png -crop 200x30+0+0 +repage -format "min=%[min] max=%[max] mean=%[mean]" info: && echo && echo "--- column profile: max intensity per x (first 60 cols) ---" && magick fps-check.png -crop 60x20+0+0 +repage -colorspace gray txt: | awk -F'[,:]' 'NR>1{print $1}' | sort -n | uniq | head -0; magick fps-check.png -crop 60x20+0+0 +repage -colorspace gray -scale 60x1! txt: | head -20


# --- L168  2026-09-21T19:21:46.728Z ---
grep -n "import" /home/tjwise/meta-wisekiosk/tools/kiosk-render-check.sh | head -20


# --- L171  2026-09-21T19:21:56.023Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh -s 30 "1080p + SHOW_FPS, no capture running"' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/probe.sh


# --- L175  2026-09-21T19:22:50.280Z ---
timeout 60 tools/kiosk-ssh.sh root@<prod> 'cat > /tmp/probe.sh && chmod +x /tmp/probe.sh && echo "probe pushed: $(wc -l < /tmp/probe.sh) lines"' < /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/probe.sh


# --- L177  2026-09-21T19:22:57.432Z ---
timeout 300 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
# Restore the panel mode no matter how this exits.
restore() {
  DISPLAY=:0 xrandr --output HDMI-1 --mode 1920x1080 --rate 60 2>&1
  sleep 3
  echo "--- restored mode: $(DISPLAY=:0 xrandr | awk '/\*/{print $1,$2}') ---"
}
trap restore EXIT INT TERM

echo "=== switching to 1280x720 ==="
DISPLAY=:0 xrandr --output HDMI-1 --mode 1280x720 --rate 60 2>&1
sleep 8
echo "mode now: $(DISPLAY=:0 xrandr | awk '/\*/{print $1,$2}')"
echo "fb geometry now: $(grep -m1 -A4 'allocated by = X' /sys/kernel/debug/dri/0/framebuffer | grep -m1 size=)"
sh /tmp/probe.sh 30 "720p scanout, 1080p surf window"
EOF


# --- L181  2026-09-21T19:23:43.910Z ---
timeout 300 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -f /tmp/fps.*.png
n=1
while [ $n -le 8 ]; do
  DISPLAY=:0 import -window root -crop 140x34+0+0 +repage /tmp/fps.$n.png 2>&1
  echo "cap $n rc=$? t=$(cut -d' ' -f1 /proc/uptime) bytes=$(wc -c < /tmp/fps.$n.png)"
  sleep 2
  n=$((n+1))
done
echo "=== base64 bundle ==="
tar cf - /tmp/fps.*.png 2>/dev/null | gzip | base64 -w 200
echo "=== END ==="
EOF


# --- L185  2026-09-21T19:24:36.036Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && rm -f fps.*.png && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlMaster=auto -o ControlPath="$HOME/.ssh/kiosk-%C" -o ControlPersist=30m 'root@<prod>:/tmp/fps.*.png' . ; echo "scp rc=$?"; ls -la fps.*.png


# --- L189  2026-09-21T19:24:46.253Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlMaster=auto -o ControlPath="$HOME/.ssh/kiosk-%C" -o ControlPersist=30m 'root@<prod>:/tmp/fps.1.png' 'root@<prod>:/tmp/fps.2.png' 'root@<prod>:/tmp/fps.3.png' 'root@<prod>:/tmp/fps.6.png' 'root@<prod>:/tmp/fps.8.png' . 2>&1; echo "scp rc=$?"; ls -la | grep fps


# --- L191  2026-09-21T19:24:53.851Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && magick montage fps.1.png fps.2.png fps.3.png fps.6.png fps.8.png -tile 1x5 -geometry +2+2 -background gray20 -filter point -resize 500% fps-series.png && echo ok && for f in fps.1.png fps.2.png fps.3.png fps.6.png fps.8.png; do printf "%s  " "$f"; magick "$f" -format "mean=%[mean] max=%[max]" info:; echo; done


# --- L198  2026-09-21T19:25:20.606Z ---
timeout 300 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -f /tmp/cal.*.png
# Continuous capture load in background for ~40s
( n=1; while [ $n -le 12 ]; do DISPLAY=:0 import -window root -crop 140x34+0+0 +repage /tmp/cal.$n.png 2>/dev/null; n=$((n+1)); done ) &
CAPPID=$!
sleep 3
sh /tmp/probe.sh 25 "1080p WITH continuous capture load (calibration)"
wait $CAPPID
echo "=== overlay values during that window (distinct file sizes) ==="
for f in /tmp/cal.*.png; do printf "%s %s bytes\n" "$f" "$(wc -c < $f)"; done
EOF


# --- L202  2026-09-21T19:26:27.389Z ---
timeout 300 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
set -e
echo "=== CONTROL: remove WEBKIT_SHOW_FPS, restart, re-capture corner ==="
cp /data/config/kiosk.conf /tmp/kiosk.conf.new
grep -v '^WEBKIT_SHOW_FPS=' /tmp/kiosk.conf.new > /tmp/kiosk.conf.new2
mv /tmp/kiosk.conf.new2 /data/config/kiosk.conf
rm -f /tmp/kiosk.conf.new
echo "keys now: $(cut -d= -f1 /data/config/kiosk.conf | tr '\n' ' ')"
systemctl restart kiosk
n=0
while [ $n -lt 24 ]; do
  sleep 5
  A=$(systemctl is-active kiosk); S=$(ps w | grep -c '[s]urf -K'); W=$(ps w | grep -c '[W]ebKitWebProcess')
  [ "$A" = "active" ] && [ "$S" -ge 1 ] && [ "$W" -ge 1 ] && { echo "up at t=$((n*5+5))s"; break; }
  n=$((n+1))
done
sleep 40
echo "=== env (SHOW_FPS should be absent) ==="
tr '\0' '\n' < /proc/$(ps w | grep '[W]ebKitWebProcess' | awk '{print $1}')/environ | grep -E 'WEBKIT' | sort
rm -f /tmp/ctl.*.png
n=1; while [ $n -le 3 ]; do
  DISPLAY=:0 import -window root -crop 140x34+0+0 +repage /tmp/ctl.$n.png 2>/dev/null
  echo "ctl $n bytes=$(wc -c < /tmp/ctl.$n.png)"
  n=$((n+1))
done
EOF


# --- L206  2026-09-21T19:26:42.378Z ---
timeout 120 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "kiosk active: $(systemctl is-active kiosk)"
echo "surf procs:   $(ps w | grep -c '[s]urf -K')"
echo "webproc:      $(ps w | grep -c '[W]ebKitWebProcess')"
echo "X:            $(ps w | grep -c '[X] :0')"
echo "config keys:  $(cut -d= -f1 /data/config/kiosk.conf | tr '\n' ' ')"
echo "uptime/load:  $(cat /proc/loadavg)"
echo "scanout fb:   $(grep -m1 -o 'fb=[0-9]*' /sys/kernel/debug/dri/0/state)"
EOF


# --- L210  2026-09-21T19:26:53.318Z ---
timeout 300 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== env: SHOW_FPS should be ABSENT now ==="
tr '\0' '\n' < /proc/$(ps w | grep '[W]ebKitWebProcess' | awk '{print $1}')/environ | grep -E 'WEBKIT' | sort
echo "(above should show only FORCE_VBLANK_TIMER)"
rm -f /tmp/ctl.1.png /tmp/ctl.2.png /tmp/ctl.3.png
for n in 1 2 3; do
  DISPLAY=:0 import -window root -crop 140x34+0+0 +repage /tmp/ctl.$n.png 2>/dev/null
  echo "ctl $n bytes=$(wc -c < /tmp/ctl.$n.png)"
  sleep 2
done
EOF


# --- L214  2026-09-21T19:27:48.178Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlMaster=auto -o ControlPath="$HOME/.ssh/kiosk-%C" 'root@<prod>:/tmp/ctl.1.png' . 2>&1 >/dev/null; magick ctl.1.png -format "control capture: min=%[min] max=%[max] mean=%[mean]\n" info:


# --- L215  2026-09-21T19:27:49.645Z ---
which python3 node websocat 2>&1; echo "---"; python3 -c "import websockets; print('py websockets', websockets.__version__)" 2>&1 | tail -1; echo "---"; node -e "try{require('ws');console.log('node ws ok')}catch(e){console.log('no node ws')}" 2>&1 | tail -1


# --- L220  2026-09-21T19:28:25.407Z ---
timeout 300 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
cp /data/config/kiosk.conf /tmp/kc.new
grep -v '^KIOSK_INSPECTOR=' /tmp/kc.new > /tmp/kc.new2
echo 'KIOSK_INSPECTOR=1' >> /tmp/kc.new2
mv /tmp/kc.new2 /data/config/kiosk.conf
rm -f /tmp/kc.new
echo "keys: $(cut -d= -f1 /data/config/kiosk.conf | tr '\n' ' ')"
echo "inspector setting: $(grep '^KIOSK_INSPECTOR' /data/config/kiosk.conf)"
systemctl restart kiosk
n=0
while [ $n -lt 30 ]; do
  sleep 5
  A=$(systemctl is-active kiosk); S=$(ps w | grep -c '[s]urf -K'); W=$(ps w | grep -c '[W]ebKitWebProcess')
  if [ "$A" = "active" ] && [ "$S" -ge 1 ] && [ "$W" -ge 1 ]; then echo "up at t=$((n*5+5))s"; break; fi
  n=$((n+1))
done
sleep 30
echo "=== inspector listening? ==="
netstat -ltn 2>/dev/null | grep 2999 || echo "(no 2999 in netstat)"
echo "=== surf env ==="
tr '\0' '\n' < /proc/$(ps w | grep '[s]urf -K' | awk '{print $1}')/environ | grep -E 'WEBKIT_INSPECTOR|KIOSK_INSPECTOR'
EOF


# --- L224  2026-09-21T19:29:15.904Z ---
ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ExitOnForwardFailure=yes -f -N -L 12999:127.0.0.1:2999 root@<prod> 2>&1; echo "tunnel rc=$?"; sleep 2; (command ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) | grep 12999


# --- L226  2026-09-21T19:29:23.255Z ---
echo "=== GET / ==="; curl -s --max-time 20 http://127.0.0.1:12999/ | head -c 2000; echo; echo "=== GET /json ==="; curl -s --max-time 20 http://127.0.0.1:12999/json | head -c 1000; echo; echo "=== GET /json/list ==="; curl -s --max-time 20 http://127.0.0.1:12999/json/list | head -c 1000; echo


# --- L230  2026-09-21T19:30:33.141Z ---
curl -sv --max-time 15 http://127.0.0.1:12999/ 2>&1 | head -25; echo "=== raw socket probe ==="; printf 'GET / HTTP/1.1\r\nHost: 127.0.0.1:12999\r\nConnection: close\r\n\r\n' | timeout 15 python3 -c "
import socket,sys
s=socket.create_connection(('127.0.0.1',12999),10)
s.sendall(sys.stdin.buffer.read())
d=b''
try:
  while True:
    c=s.recv(4096)
    if not c: break
    d+=c
except Exception as e: print('err',e)
print('bytes:',len(d)); print(d[:600])"


# --- L234  2026-09-21T19:31:17.868Z ---
timeout 60 python3 -c "
import socket,base64,os
for path in ['/','/socket','/devtools/page/1','/inspector']:
    try:
        s=socket.create_connection(('127.0.0.1',12999),8); s.settimeout(8)
        k=base64.b64encode(os.urandom(16)).decode()
        req=('GET %s HTTP/1.1\r\nHost: 127.0.0.1:12999\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
             'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n')%(path,k)
        s.sendall(req.encode())
        d=s.recv(4096)
        print(repr(path), '->', d[:200] if d else b'(no data)')
        s.close()
    except Exception as e:
        print(repr(path),'-> ERR',e)
"


# --- L238  2026-09-21T19:32:06.001Z ---
timeout 300 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
cp /data/config/kiosk.conf /tmp/kc.a
grep -v '^WEBKIT_INSPECTOR_HTTP_SERVER=' /tmp/kc.a > /tmp/kc.b
echo 'WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:2998' >> /tmp/kc.b
mv /tmp/kc.b /data/config/kiosk.conf
rm -f /tmp/kc.a
echo "keys: $(cut -d= -f1 /data/config/kiosk.conf | tr '\n' ' ')"
systemctl restart kiosk
n=0
while [ $n -lt 30 ]; do
  sleep 5
  A=$(systemctl is-active kiosk); S=$(ps w | grep -c '[s]urf -K'); W=$(ps w | grep -c '[W]ebKitWebProcess')
  if [ "$A" = "active" ] && [ "$S" -ge 1 ] && [ "$W" -ge 1 ]; then echo "up at t=$((n*5+5))s"; break; fi
  n=$((n+1))
done
sleep 30
echo "=== listening ports ==="
netstat -ltn 2>/dev/null | grep -E '299[89]' || echo "(none)"
EOF


# --- L242  2026-09-21T19:32:54.155Z ---
ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ExitOnForwardFailure=yes -f -N -L 12998:127.0.0.1:2998 root@<prod> 2>&1 | tail -1; sleep 2; echo "=== GET / ==="; curl -s --max-time 20 http://127.0.0.1:12998/ | head -c 1500; echo; echo "=== GET /json/list ==="; curl -s --max-time 20 http://127.0.0.1:12998/json/list | head -c 800; echo


# --- L248  2026-09-21T19:33:27.966Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > expr1.js <<'EOF'
(function(){
  return JSON.stringify({
    reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
    noPreference: matchMedia('(prefers-reduced-motion: no-preference)').matches,
    dpr: devicePixelRatio,
    inner: [innerWidth, innerHeight],
    screen: [screen.width, screen.height],
    ua: navigator.userAgent.slice(0,80),
    animCount: (document.getAnimations ? document.getAnimations().length : 'n/a')
  });
})()
EOF
timeout 90 python3 wsinspect.py /socket/1/1/WebPage expr1.js 45


# --- L252  2026-09-21T19:33:41.822Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > discover.py <<'PYEOF'
import json, time, sys
sys.argv = ['x']
exec(open('wsinspect.py').read().replace('main()', '', 1))
import socket
s = socket.create_connection((HOST, PORT), 15); s.settimeout(20)
rest = handshake(s, '/socket/1/1/WebPage')
r = Reader(s, rest)
send_text(s, json.dumps({"id": 1, "method": "Inspector.enable"}))
end = time.time() + 12
while time.time() < end:
    try:
        op, p = r.frame()
    except Exception as e:
        print("read end:", e); break
    if op == 1:
        t = p.decode('utf-8', 'replace')
        print(t[:500])
PYEOF
timeout 60 python3 discover.py


# --- L257  2026-09-21T19:33:56.066Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > discover.py <<'PYEOF'
import json, time, socket
from wsinspect import HOST, PORT, handshake, send_text, Reader

s = socket.create_connection((HOST, PORT), 15); s.settimeout(15)
r = Reader(s, handshake(s, '/socket/1/1/WebPage'))
for i, m in enumerate([{"id":1,"method":"Inspector.enable"},
                       {"id":2,"method":"Target.exists"},
                       {"id":3,"method":"Console.enable"}]):
    send_text(s, json.dumps(m))
end = time.time() + 12
while time.time() < end:
    try:
        op, p = r.frame()
    except Exception as e:
        print("read end:", e); break
    if op == 1:
        print(p.decode('utf-8','replace')[:400])
PYEOF
timeout 60 python3 discover.py


# --- L263  2026-09-21T19:34:31.692Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && timeout 120 python3 inspect_eval.py expr1.js 60


# --- L267  2026-09-21T19:34:56.141Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > expr2.js <<'EOF'
new Promise(function(resolve){
  var ts = [], wall = [], N = 150;
  function step(t){
    ts.push(t); wall.push(performance.now());
    if (ts.length < N) requestAnimationFrame(step);
    else {
      var di = [], dw = [];
      for (var i=1;i<ts.length;i++){ di.push(+(ts[i]-ts[i-1]).toFixed(2)); dw.push(+(wall[i]-wall[i-1]).toFixed(2)); }
      var mean = function(a){return a.reduce(function(x,y){return x+y},0)/a.length;};
      var m = mean(dw);
      var sd = Math.sqrt(mean(dw.map(function(x){return (x-m)*(x-m);})));
      var sorted = dw.slice().sort(function(a,b){return a-b;});
      resolve(JSON.stringify({
        frames: ts.length,
        span_ms: +(wall[wall.length-1]-wall[0]).toFixed(1),
        raf_rate_hz: +(1000*(ts.length-1)/(wall[wall.length-1]-wall[0])).toFixed(2),
        wall_interval_mean_ms: +m.toFixed(2),
        wall_interval_sd_ms: +sd.toFixed(2),
        min_ms: sorted[0], p50: sorted[Math.floor(sorted.length*0.5)],
        p90: sorted[Math.floor(sorted.length*0.9)], max_ms: sorted[sorted.length-1],
        first40_wall_intervals: dw.slice(0,40)
      }));
    }
  }
  requestAnimationFrame(step);
})
EOF
timeout 180 python3 inspect_eval.py expr2.js 150


# --- L271  2026-09-21T19:35:11.795Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > dbg.py <<'PYEOF'
import json
from inspect_eval import run
print(json.dumps(run(open('expr2.js').read(), 150), indent=1)[:4000])
PYEOF
timeout 200 python3 dbg.py


# --- L275  2026-09-21T19:35:32.346Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > start_collect.js <<'EOF'
(function(){
  window.__fd = {ts: [], wall: [], done: false};
  var N = 200;
  function step(t){
    window.__fd.ts.push(t);
    window.__fd.wall.push(performance.now());
    if (window.__fd.ts.length < N) requestAnimationFrame(step);
    else window.__fd.done = true;
  }
  requestAnimationFrame(step);
  return 'collector armed, N=' + N;
})()
EOF
cat > read_collect.js <<'EOF'
(function(){
  var f = window.__fd;
  if (!f) return JSON.stringify({error:'no collector'});
  var ts=f.ts, wall=f.wall;
  if (ts.length < 3) return JSON.stringify({error:'too few frames', n: ts.length});
  var dw=[]; for (var i=1;i<wall.length;i++) dw.push(+(wall[i]-wall[i-1]).toFixed(2));
  var mean=function(a){return a.reduce(function(x,y){return x+y},0)/a.length;};
  var m=mean(dw), sd=Math.sqrt(mean(dw.map(function(x){return (x-m)*(x-m);})));
  var s=dw.slice().sort(function(a,b){return a-b;});
  return JSON.stringify({
    done: f.done, frames: ts.length,
    span_ms: +(wall[wall.length-1]-wall[0]).toFixed(1),
    raf_rate_hz: +(1000*(ts.length-1)/(wall[wall.length-1]-wall[0])).toFixed(2),
    interval_mean_ms: +m.toFixed(2), interval_sd_ms: +sd.toFixed(2),
    min_ms: s[0], p50_ms: s[Math.floor(s.length*0.5)],
    p90_ms: s[Math.floor(s.length*0.9)], max_ms: s[s.length-1],
    first30: dw.slice(0,30)
  });
})()
EOF
echo "--- arming collector ---"
timeout 90 python3 inspect_eval.py start_collect.js 60


# --- L277  2026-09-21T19:35:43.492Z ---
sleep 20; cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && timeout 90 python3 inspect_eval.py read_collect.js 60


# --- L281  2026-09-21T19:37:03.635Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
WP=$(ps w | grep '[W]ebKitWebProcess' | awk '{print $1}')
XP=$(ps w | grep '[X] :0' | awk '{print $1}')
SP=$(ps w | grep '[s]urf -K' | awk '{print $1}')
echo "pids: web=$WP X=$XP surf=$SP"
snap() { for t in /proc/$1/task/*; do
    [ -r "$t/stat" ] || continue
    n=$(cat "$t/comm" 2>/dev/null)
    c=$(awk '{print $14+$15}' "$t/stat" 2>/dev/null)
    echo "$(basename $t) $n $c"
  done; }
C1=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8}' /proc/stat)
snap $WP > /tmp/w1; snap $XP > /tmp/x1; snap $SP > /tmp/s1
sleep 25
C2=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8}' /proc/stat)
snap $WP > /tmp/w2; snap $XP > /tmp/x2; snap $SP > /tmp/s2
TOT=$((C2-C1))
report() {
  echo "--- $2 (threads using >0.5% of the core) ---"
  join -j 1 -o 0,1.2,1.3,2.3 "$1.1" "$1.2" 2>/dev/null | awk -v tot=$TOT '{d=$4-$3; p=d/tot*100; if(p>0.5) printf "  tid=%-6s %-18s %5.1f%%\n", $1, $2, p}' | sort -k3 -rn
}
echo "total cpu jiffies in window: $TOT"
report /tmp/w "WebKitWebProcess"
report /tmp/x "Xorg"
report /tmp/s "surf (UIProcess)"
EOF


# --- L285  2026-09-21T19:37:45.384Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
WP=$(ps w | grep '[W]ebKitWebProcess' | awk '{print $1}')
XP=$(ps w | grep '[X] :0' | awk '{print $1}')
SP=$(ps w | grep '[s]urf -K' | awk '{print $1}')
snap() { for t in /proc/$1/task/*; do
    [ -r "$t/stat" ] || continue
    printf '%s %s %s\n' "$(basename $t)" "$(cat $t/comm 2>/dev/null)" "$(awk '{print $14+$15}' $t/stat 2>/dev/null)"
  done; }
C1=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8}' /proc/stat)
snap $WP > /tmp/w1; snap $XP > /tmp/x1; snap $SP > /tmp/s1
sleep 25
C2=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8}' /proc/stat)
snap $WP > /tmp/w2; snap $XP > /tmp/x2; snap $SP > /tmp/s2
TOT=$((C2-C1))
echo "window cpu jiffies = $TOT  (100% = $TOT)"
rep() {
  echo "--- $2 ---"
  awk -v tot=$TOT 'NR==FNR{a[$1]=$3; n[$1]=$2; next} ($1 in a){d=$3-a[$1]; p=d/tot*100; if(p>0.3) printf "  %-8s %-20s %5.1f%%\n",$1,n[$1],p}' "$1"1 "$1"2 | sort -k3 -rn
}
rep /tmp/w "WebKitWebProcess threads"
rep /tmp/x "Xorg threads"
rep /tmp/s "surf UIProcess threads"
EOF


# --- L289  2026-09-21T19:38:44.434Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > expr3.js <<'EOF'
(function(){
  var out = [];
  var anims = document.getAnimations ? document.getAnimations() : [];
  anims.forEach(function(a, i){
    var t = a.effect && a.effect.target;
    var info = {idx:i, playState:a.playState, type:a.constructor.name};
    if (a.animationName) info.name = a.animationName;
    if (t) {
      var cs = getComputedStyle(t);
      var r = t.getBoundingClientRect();
      info.target = t.tagName + (t.className ? '.' + String(t.className).slice(0,40) : '');
      info.rect = [Math.round(r.width), Math.round(r.height)];
      info.scrollW = t.scrollWidth;
      info.offsetW = t.offsetWidth;
      info.willChange = cs.willChange;
      info.transform = cs.transform;
      info.animDur = cs.animationDuration;
      info.parentScrollW = t.parentElement ? t.parentElement.scrollWidth : null;
      info.parentClass = t.parentElement ? String(t.parentElement.className).slice(0,40) : null;
    }
    out.push(info);
  });
  // any element wider than the 2048 VC4 texture limit
  var wide = [];
  document.querySelectorAll('*').forEach(function(e){
    var w = e.scrollWidth, h = e.scrollHeight;
    if (w > 2048 || h > 2048) {
      var cs = getComputedStyle(e);
      wide.push({tag:e.tagName, cls:String(e.className).slice(0,45), scrollW:w, scrollH:h,
                 willChange:cs.willChange, transform:cs.transform.slice(0,40),
                 anim:cs.animationName});
    }
  });
  return JSON.stringify({animations: out, wider_than_2048: wide, totalEls: document.querySelectorAll('*').length}, null, 1);
})()
EOF
timeout 120 python3 inspect_eval.py expr3.js 90


# --- L293  2026-09-21T19:39:19.441Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > arm2.js <<'EOF'
(function(){
  window.__t2 = {raf:[], tmo:[], startedAt: performance.now()};
  var NR = 60, NT = 400;
  function rstep(){ window.__t2.raf.push(performance.now());
    if (window.__t2.raf.length < NR) requestAnimationFrame(rstep); }
  requestAnimationFrame(rstep);
  function tstep(){ window.__t2.tmo.push(performance.now());
    if (window.__t2.tmo.length < NT) setTimeout(tstep, 0); }
  setTimeout(tstep, 0);
  return 'armed raf/setTimeout comparator';
})()
EOF
cat > read2.js <<'EOF'
(function(){
  var d = window.__t2; if(!d) return JSON.stringify({error:'not armed'});
  function stats(a){
    if (a.length < 3) return {n:a.length};
    var iv=[]; for(var i=1;i<a.length;i++) iv.push(a[i]-a[i-1]);
    var mean=iv.reduce(function(x,y){return x+y},0)/iv.length;
    var sd=Math.sqrt(iv.map(function(x){return (x-mean)*(x-mean);}).reduce(function(x,y){return x+y},0)/iv.length);
    var s=iv.slice().sort(function(x,y){return x-y;});
    return {n:a.length, span_ms:+(a[a.length-1]-a[0]).toFixed(0), rate_hz:+(1000*(a.length-1)/(a[a.length-1]-a[0])).toFixed(2),
            mean_ms:+mean.toFixed(2), sd_ms:+sd.toFixed(2), min:+s[0].toFixed(2),
            p50:+s[Math.floor(s.length/2)].toFixed(2), max:+s[s.length-1].toFixed(2)};
  }
  return JSON.stringify({raf: stats(d.raf), setTimeout0: stats(d.tmo)}, null, 1);
})()
EOF
timeout 90 python3 inspect_eval.py arm2.js 60


# --- L295  2026-09-21T19:39:26.719Z ---
sleep 45; cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && timeout 120 python3 inspect_eval.py read2.js 90


# --- L297  2026-09-21T19:39:31.650Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && until [ -f /tmp/claude-1000/waitdone ]; do sleep 10; touch /tmp/claude-1000/waitdone; done; rm -f /tmp/claude-1000/waitdone; timeout 120 python3 inspect_eval.py read2.js 90


# --- L303  2026-09-21T19:39:44.977Z ---
until [ -s /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b724k785e.output ]; do sleep 5; done; cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/b724k785e.output


# --- L307  2026-09-21T19:40:18.155Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > pause.js <<'EOF'
(function(){ var a=document.getAnimations(); a.forEach(function(x){x.pause();});
  return 'paused '+a.length+' animations; states='+a.map(function(x){return x.playState;}).join(','); })()
EOF
cat > play.js <<'EOF'
(function(){ var a=document.getAnimations(); a.forEach(function(x){x.play();});
  return 'resumed '+a.length+' animations; states='+a.map(function(x){return x.playState;}).join(','); })()
EOF
timeout 90 python3 inspect_eval.py pause.js 60


# --- L311  2026-09-21T19:40:24.243Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh /tmp/probe.sh 30 "ANIMATIONS PAUSED (inspector attached)"'


# --- L315  2026-09-21T19:41:23.887Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > armmut.js <<'EOF'
(function(){
  window.__mu = {n:0, t0: performance.now(), tags:{}, chars:0, attrs:0, childs:0};
  var o = new MutationObserver(function(recs){
    window.__mu.n += recs.length;
    recs.forEach(function(r){
      var t = (r.target.nodeName||'?');
      window.__mu.tags[t] = (window.__mu.tags[t]||0)+1;
      if (r.type==='characterData') window.__mu.chars++;
      else if (r.type==='attributes') window.__mu.attrs++;
      else window.__mu.childs++;
    });
  });
  o.observe(document.documentElement, {subtree:true, childList:true, attributes:true, characterData:true});
  window.__muObs = o;
  return 'mutation observer armed';
})()
EOF
cat > readmut.js <<'EOF'
(function(){
  var m = window.__mu; if(!m) return JSON.stringify({error:'not armed'});
  var dt = (performance.now()-m.t0)/1000;
  var top = Object.keys(m.tags).map(function(k){return [k,m.tags[k]];})
            .sort(function(a,b){return b[1]-a[1];}).slice(0,8);
  return JSON.stringify({seconds:+dt.toFixed(1), mutations:m.n, per_sec:+(m.n/dt).toFixed(1),
    characterData:m.chars, attributes:m.attrs, childList:m.childs, topTargets:top,
    title:document.title, url:location.href.replace(/\/\/[^/]+/,'//<redacted>'),
    bodyTextLen:document.body.innerText.length,
    visibility:document.visibilityState}, null, 1);
})()
EOF
timeout 90 python3 inspect_eval.py armmut.js 60


# --- L317  2026-09-21T19:41:31.374Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && until [ -f /tmp/claude-1000/wd2 ]; do sleep 20; touch /tmp/claude-1000/wd2; done; rm -f /tmp/claude-1000/wd2; timeout 120 python3 inspect_eval.py readmut.js 90


# --- L319  2026-09-21T19:41:36.861Z ---
until [ -s /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bz2lc7uvz.output ]; do sleep 5; done; cat /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/tasks/bz2lc7uvz.output


# --- L323  2026-09-21T19:42:30.616Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && cat > blank.js <<'EOF'
(function(){ var b=document.body; window.__savedVis=b.style.visibility;
  b.style.visibility='hidden'; return 'body hidden; prev='+JSON.stringify(window.__savedVis); })()
EOF
cat > unblank.js <<'EOF'
(function(){ var b=document.body; b.style.visibility=window.__savedVis||'';
  return 'body visibility restored to '+JSON.stringify(b.style.visibility)+' computed='+getComputedStyle(b).visibility; })()
EOF
timeout 90 python3 inspect_eval.py blank.js 60


# --- L325  2026-09-21T19:42:36.339Z ---
timeout 180 tools/kiosk-ssh.sh root@<prod> 'sh /tmp/probe.sh 25 "BODY HIDDEN + animations paused"'


# --- L329  2026-09-21T19:43:23.173Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b && timeout 90 python3 inspect_eval.py unblank.js 60 && timeout 90 python3 inspect_eval.py play.js 60


# --- L333  2026-09-21T19:44:41.113Z ---
timeout 300 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== building config: original 3 keys MINUS WEBKIT_FORCE_VBLANK_TIMER ==="
grep -v '^WEBKIT_FORCE_VBLANK_TIMER=' /data/config/kiosk.conf.bak-stutter > /tmp/kc.test
mv /tmp/kc.test /data/config/kiosk.conf
echo "keys: $(cut -d= -f1 /data/config/kiosk.conf | tr '\n' ' ')"
systemctl restart kiosk
n=0
while [ $n -lt 30 ]; do
  sleep 5
  A=$(systemctl is-active kiosk); S=$(ps w | grep -c '[s]urf -K'); W=$(ps w | grep -c '[W]ebKitWebProcess')
  echo "t=$((n*5+5))s active=$A surf=$S webproc=$W"
  [ "$A" = "active" ] && [ "$S" -ge 1 ] && [ "$W" -ge 1 ] && break
  n=$((n+1))
done
sleep 35
echo "=== SIGFPE / crash check ==="
journalctl -u kiosk --no-pager -n 200 2>/dev/null | grep -iE 'sigfpe|signal|segv|core|crash|floating' | tail -n 10 || echo "(no crash lines)"
echo "=== web process alive? ==="
ps w | grep '[W]ebKitWebProcess' | head -n 2
echo "=== env (FORCE_VBLANK_TIMER should be ABSENT) ==="
tr '\0' '\n' < /proc/$(ps w | grep '[W]ebKitWebProcess' | awk '{print $1}')/environ | grep -E 'WEBKIT' || echo "(no WEBKIT vars - as intended)"
EOF


# --- L337  2026-09-21T19:45:51.935Z ---
timeout 300 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
echo "=== RESTORING original config from backup ==="
cp /data/config/kiosk.conf.bak-stutter /data/config/kiosk.conf
echo "keys: $(cut -d= -f1 /data/config/kiosk.conf | tr '\n' ' ')"
echo "inspector line: $(grep '^KIOSK_INSPECTOR' /data/config/kiosk.conf)"
echo "vblank line:    $(grep '^WEBKIT_FORCE_VBLANK_TIMER' /data/config/kiosk.conf)"
systemctl restart kiosk
n=0
while [ $n -lt 36 ]; do
  sleep 5
  A=$(systemctl is-active kiosk); S=$(ps w | grep -c '[s]urf -K'); W=$(ps w | grep -c '[W]ebKitWebProcess')
  echo "t=$((n*5+5))s active=$A surf=$S webproc=$W"
  [ "$A" = "active" ] && [ "$S" -ge 1 ] && [ "$W" -ge 1 ] && break
  n=$((n+1))
done
EOF


# --- L341  2026-09-21T19:46:10.777Z ---
pkill -f "L 12999:127.0.0.1:2999" 2>/dev/null; pkill -f "L 12998:127.0.0.1:2998" 2>/dev/null; echo "tunnels closed"; timeout 240 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
sleep 30
echo "=== no inspector port should be listening ==="
netstat -ltn 2>/dev/null | grep -E '299[89]' || echo "(none listening - correct)"
echo "=== no recent FPE ==="
journalctl -u kiosk --no-pager -n 60 2>/dev/null | grep -ciE 'floating point' || true
sh /tmp/probe.sh 30 "FINAL BASELINE - config restored, no inspector, no capture"
EOF


# --- L345  2026-09-21T19:46:20.782Z ---
timeout 240 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
sleep 30
echo "=== inspector ports (should be none) ==="
netstat -ltn 2>/dev/null | grep -E '299[89]' || echo "(none listening - correct)"
echo "=== floating point exceptions in last 60 journal lines ==="
journalctl -u kiosk --no-pager -n 60 2>/dev/null | grep -c -i 'floating point' || echo 0
sh /tmp/probe.sh 30 "FINAL BASELINE - config restored, no inspector, no capture"
EOF


# --- L349  2026-09-21T19:47:33.032Z ---
ps -o pid=,args= -u "$USER" | grep 'ssh .*-N -L 1299' | grep -v grep


# --- L350  2026-09-21T19:47:33.877Z ---
timeout 300 tools/kiosk-render-check.sh root@<prod> 2>&1 | tail -n 12


# --- L355  2026-09-21T19:47:55.382Z ---
kill 717870 718997 2>&1; sleep 1; ps -o pid=,args= -u "$USER" | grep 'ssh .*-N -L 1299' | grep -v grep || echo "tunnels gone"


# --- L357  2026-09-21T19:48:02.749Z ---
timeout 120 tools/kiosk-ssh.sh root@<prod> 'sh -s' <<'EOF'
rm -f /tmp/probe.sh /tmp/w1 /tmp/w2 /tmp/x1 /tmp/x2 /tmp/s1 /tmp/s2 /tmp/kc.a /tmp/kc.b /tmp/kc.new /tmp/kiosk.conf.new
for f in /tmp/fps.1.png /tmp/fps.2.png /tmp/fps.3.png /tmp/fps.4.png /tmp/fps.5.png /tmp/fps.6.png /tmp/fps.7.png /tmp/fps.8.png; do rm -f "$f"; done
n=1; while [ $n -le 12 ]; do rm -f /tmp/cal.$n.png; n=$((n+1)); done
rm -f /tmp/ctl.1.png /tmp/ctl.2.png /tmp/ctl.3.png
echo "leftover diagnostic files in /tmp:"; ls /tmp | grep -E 'probe|fps|cal|ctl|kc\.' || echo "(none)"
echo "=== FINAL STATE ==="
echo "kiosk:     $(systemctl is-active kiosk)"
echo "config:    $(cut -d= -f1 /data/config/kiosk.conf | tr '\n' ' ')"
echo "inspector: $(grep '^KIOSK_INSPECTOR' /data/config/kiosk.conf)"
echo "vblank:    $(grep '^WEBKIT_FORCE_VBLANK_TIMER' /data/config/kiosk.conf)"
echo "backup kept at /data/config/kiosk.conf.bak-stutter: $(cut -d= -f1 /data/config/kiosk.conf.bak-stutter | tr '\n' ' ')"
echo "diff vs backup: $(diff /data/config/kiosk.conf /data/config/kiosk.conf.bak-stutter > /dev/null 2>&1 && echo IDENTICAL || echo DIFFERS)"
echo "mode:      $(DISPLAY=:0 xrandr 2>/dev/null | awk '/\*/{print $1,$2}')"
echo "load:      $(cut -d' ' -f1-3 /proc/loadavg)"
EOF


# --- L365  2026-09-21T19:50:21.169Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && echo "--- scanning deliverable for identity leaks ---" && command grep -nE '192\.168\.|<bench-hostname>|B8:27:EB|58e33d6d|<wifi-ssid>|22242ba3' stutter-profile.md && echo "LEAK FOUND" || echo "clean: no address/hostname/MAC/machine-id/SSID"


# --- L367  2026-09-21T19:50:22.867Z ---
timeout 120 tools/kiosk-ssh.sh root@<prod> 'echo "kiosk=$(systemctl is-active kiosk) surf=$(ps w | grep -c "[s]urf -K") web=$(ps w | grep -c "[W]ebKitWebProcess") X=$(ps w | grep -c "[X] :0") load=$(cut -d" " -f1 /proc/loadavg)"'
