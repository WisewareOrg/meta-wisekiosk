#!/bin/sh
# Kiosk soak sampler.
#
#   kiosk-soak.sh              take one sample
#   kiosk-soak.sh --summary [N]   report over the last N samples (default: all)
#
# Env: KIOSK_SOAK_LOG (default /data/kiosk-soak.log), KIOSK_SOAK_MAXLINES (default 20000).
# busybox has no `ps -eo` or `df --output`, and its `free -m` reports KB, so memory is divided to
# MB here.
#
# The fields that are not self-evident from the printf below:
#   boot       first 8 of boot_id. A change means the device rebooted, and the
#              samples either side are not one series
#   pid        main browser pid. A change means the browser restarted; `none`
#              means it was not running at that sample
#   nproc      processes in the browser family (kiosk-browser plus its WPE children)
#   rss_total  RSS across that whole family, and the memory number that matters
#              -- the renderer is a separate process and holds most of it
#   thr        vcgencmd get_throttled. Anything but 0x0 means it throttled at
#              some point SINCE BOOT, not that it is throttling now
#   ent        entropy pool. Low is expected; the image has no rngd
#
# Read a --summary in this order, weakest evidence last:
#   1. reboots and browser restarts: non-zero means the memory series is really two series
#   2. samples w/o browser: the kiosk was down at those samples
#   3. the shape of rss_total across the window, read manually against the log
#   4. the slope, last. The endpoint delta is not a rate, and one line fitted through a step
#      reports the step as a rate; compare samples at matched page states far apart.
set -u
LOG=${KIOSK_SOAK_LOG:-/data/kiosk-soak.log}
MAXLINES=${KIOSK_SOAK_MAXLINES:-20000}

if [ "${1:-}" = "--summary" ]; then
  N=${2:-0}
  [ "$N" -gt 0 ] 2>/dev/null && SRC=$(tail -n "$N" "$LOG") || SRC=$(cat "$LOG")
  printf '%s\n' "$SRC" | awk '
    { for (i = 1; i <= NF; i++) { split($i, kv, "="); v[kv[1]] = kv[2] }
      n++
      if (first == "") { first = v["ts"]; frss = v["rss_total"]; fboot = v["boot"] }
      last = v["ts"]; lrss = v["rss_total"]
      # A gap is a delta above 450 s, 1.5x the 300 s timer cadence.
      if (prevts != "" && v["ts"] - prevts > 450) { gaps++; if (v["ts"] - prevts > maxgap) maxgap = v["ts"] - prevts }
      prevts = v["ts"]
      if (v["boot"] != fboot && !seen[v["boot"]]++) reboots++
      if (v["pid"] == "none") down++
      else { if (prevpid != "" && v["pid"] != prevpid) restarts++; prevpid = v["pid"] }
      if (v["rss_total"] + 0 > maxrss || maxrss == 0) maxrss = v["rss_total"] + 0
      if (minrss == 0 || v["rss_total"] + 0 < minrss) minrss = v["rss_total"] + 0
      if (v["load1"] + 0 > maxload) maxload = v["load1"] + 0
      if (v["temp"] + 0 > maxtemp) maxtemp = v["temp"] + 0
      if (v["thr"] != "0x0") thr++
    }
    END {
      hours = (last - first) / 3600
      printf "  samples          %d over %.1f h\n", n, hours
      printf "  reboots          %d\n", reboots + 0
      printf "  browser restarts %d\n", restarts + 0
      if (gaps > 0) printf "  ts gaps          %d (largest %ds) <-- series not contiguous\n", gaps + 0, maxgap + 0
      printf "  samples w/o browser  %d %s\n", down + 0, (down > 0 ? "<-- kiosk was down" : "")
      printf "  rss_total range  %d .. %d kB\n", minrss, maxrss
      printf "  rss_total ends   %d -> %d kB (endpoint delta %+d -- NOT a rate)\n", frss, lrss, lrss - frss
      if (reboots > 0 || gaps > 0) {
        reason = (reboots > 0 && gaps > 0) ? "reboot + ts gap" : (reboots > 0 ? "reboot" : "ts gap")
        printf "  slope            n/a  (%s -- memory series is not one contiguous run)\n", reason
      }
      else if (n == 2) printf "  slope            n/a  (two-point series -- endpoint delta above is the only estimate)\n"
      else if (hours > 0.5) printf "  slope            %+.1f kB/h  (n=%d)\n", (lrss - frss) / hours, n
      printf "  peak temp        %.1f C\n", maxtemp
      printf "  peak load1       %.2f  (includes the sampler wake-up itself)\n", maxload
      printf "  throttled        %d sample(s) with thr != 0x0\n", thr + 0
    }'
  exit 0
fi

# ----------------------------------------------------------------- sample mode
COMM=kiosk-browser

# pidof, not pgrep -x: busybox's pgrep -x matches the full path the launcher runs as.
PID=$(pidof "$COMM")

# The browser family is kiosk-browser plus its WPE* children, found by walking /proc.
NPROC=0; RSS_TOTAL=0
for d in /proc/[0-9]*; do
  c=$(cat "$d/comm" 2>/dev/null) || continue
  case "$c" in
    WPE*|"$COMM")
      r=$(awk '/^VmRSS/{print $2}' "$d/status" 2>/dev/null)
      [ -n "$r" ] && { NPROC=$((NPROC + 1)); RSS_TOTAL=$((RSS_TOTAL + r)); } ;;
  esac
done

RSS_MAIN=0
[ -n "$PID" ] && RSS_MAIN=$(awk '/^VmRSS/{print $2}' "/proc/$PID/status" 2>/dev/null)

read -r L1 L5 L15 _ < /proc/loadavg
UP=$(cut -d. -f1 /proc/uptime)
BOOT=$(cut -c1-8 /proc/sys/kernel/random/boot_id)
TEMP=$(awk '{printf "%.1f", $1 / 1000}' /sys/class/thermal/thermal_zone0/temp)
THR=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
ENT=$(cat /proc/sys/kernel/random/entropy_avail)
DISK=$(df / | awk 'NR==2{print $5}' | tr -d ' %')
MU=$(free | awk '/^Mem/{printf "%d", $3 / 1024}')
MA=$(free | awk '/^Mem/{printf "%d", $7 / 1024}')

printf 'ts=%s iso=%s boot=%s up=%s load1=%s load5=%s load15=%s temp=%s thr=%s memused=%s memavail=%s ent=%s disk=%s browser=%s pid=%s nproc=%s rss_main=%s rss_total=%s\n' \
  "$(date +%s)" "$(date +%Y-%m-%dT%H:%M:%S%z)" "$BOOT" "$UP" "$L1" "$L5" "$L15" "$TEMP" "${THR:-unknown}" \
  "$MU" "$MA" "$ENT" "$DISK" "$COMM" "${PID:-none}" "$NPROC" "$RSS_MAIN" "$RSS_TOTAL" \
  >> "$LOG"

# Trim the log to MAXLINES through a temp file and mv, so a reader never sees a truncated file.
lines=$(wc -l < "$LOG")
if [ "$lines" -gt "$MAXLINES" ]; then
  tail -n "$MAXLINES" "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
