#!/bin/sh
# Presentation-pipeline probe for the wisekiosk board. POSIX/busybox only.
# Usage: probe.sh [window_seconds] [label]
# Reports: panel vblank rate, V3D render-job rate, per-process CPU, idle, and
# the scanout framebuffer identity (the page-flip discriminator).
W=${1:-20}
LABEL=${2:-unlabelled}

irq()  { grep "$1" /proc/interrupts | tr -s ' ' | cut -d' ' -f3; }
pidof_re() { ps w | grep "$1" | grep -v grep | awk '{print $1}' | head -n 1; }
pcpu() { [ -n "$1" ] && awk '{print $14+$15}' /proc/"$1"/stat 2>/dev/null || echo 0; }

XP=$(pidof_re '^ *[0-9]* root .* X :0')
SP=$(pidof_re 'surf -K')
WP=$(pidof_re 'WebKitWebProcess')

echo "### probe: $LABEL   window=${W}s"
echo "pids: X=$XP surf=$SP webproc=$WP"
echo "mode: $(DISPLAY=:0 xrandr 2>/dev/null | awk '/\*/{print $1, $2}')"
echo "screen: $(DISPLAY=:0 xrandr 2>/dev/null | awk '/^Screen 0/{print $8, $9, $10}')"

V1=$(irq 'vc4 firmware kms'); G1=$(irq ' vc4$'); T1=$(cut -d' ' -f1 /proc/uptime)
X1=$(pcpu "$XP"); S1=$(pcpu "$SP"); W1=$(pcpu "$WP")
I1=$(awk '/^cpu /{print $5}' /proc/stat)
C1=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8}' /proc/stat)
sleep "$W"
V2=$(irq 'vc4 firmware kms'); G2=$(irq ' vc4$'); T2=$(cut -d' ' -f1 /proc/uptime)
X2=$(pcpu "$XP"); S2=$(pcpu "$SP"); W2=$(pcpu "$WP")
I2=$(awk '/^cpu /{print $5}' /proc/stat)
C2=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8}' /proc/stat)

E=$(awk "BEGIN{printf \"%.2f\", $T2-$T1}")
echo "elapsed_s         = $E"
echo "vblank_rate_hz    = $(awk "BEGIN{printf \"%.2f\", ($V2-$V1)/($T2-$T1)}")   (delta=$((V2-V1)))"
echo "v3d_job_rate_hz   = $(awk "BEGIN{printf \"%.2f\", ($G2-$G1)/($T2-$T1)}")   (delta=$((G2-G1)))"
echo "X_cpu_pct         = $(awk "BEGIN{printf \"%.1f\", ($X2-$X1)/($C2-$C1)*100}")"
echo "surf_cpu_pct      = $(awk "BEGIN{printf \"%.1f\", ($S2-$S1)/($C2-$C1)*100}")"
echo "webproc_cpu_pct   = $(awk "BEGIN{printf \"%.1f\", ($W2-$W1)/($C2-$C1)*100}")"
echo "idle_pct          = $(awk "BEGIN{printf \"%.1f\", ($I2-$I1)/($C2-$C1)*100}")"
echo "loadavg           = $(cut -d' ' -f1-3 /proc/loadavg)"
echo "scanout_fb        = $(grep -m1 -o 'fb=[0-9]*' /sys/kernel/debug/dri/0/state)"
echo "X_fb_count        = $(grep -c 'allocated by = X' /sys/kernel/debug/dri/0/framebuffer)"
echo "fb_geometry       = $(grep -m1 -A4 'allocated by = X' /sys/kernel/debug/dri/0/framebuffer | grep -m1 size=)"
echo "CmaFree_kB        = $(awk '/CmaFree/{print $2}' /proc/meminfo)"
