#!/bin/bash
# A96 + A98 bench network read (bench-net-read.md). usage: netread.sh STEP [STEP...]  (1..5). Reads only; appends to bench-net-read.txt.
set -u
O=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/78a61228-d84d-4353-990b-bf04f02f1d7b/scratchpad/orch
D=/home/tjwise/.claude/deliverables/78a61228-d84d-4353-990b-bf04f02f1d7b
OUT=$D/bench-net-read.txt
B=${BENCH:?the bench board address}
SSHO=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o LogLevel=ERROR)
mask() { sed -E 's/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/<addr>/g; s/<hostname>/<host>/g'; }
t() { date +%T.%N | cut -c1-12; }
h() { echo; echo "== $(t) $*"; }
beside() { echo "beside: containers: $(docker ps --format '{{.Image}}' 2>/dev/null | tr '\n' ' '); bench-run: $(systemctl --user is-active bench-run.service); prod: $(systemctl --user is-active bench-run@prod.service); MemAvailable $(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) MB; host load $(cut -d' ' -f1-3 /proc/loadavg)"; }
base() { # step 1 / 5
  h "step $1: baseline (board reads, then host ping 20 x 0.5 s)"; beside
  ssh "${SSHO[@]}" root@$B 'cat /proc/net/wireless; ip -s link show wlan0; cat /proc/loadavg; if command -v iw >/dev/null; then iw dev wlan0 link; else echo "iw: not in the image"; fi
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
cat /sys/class/hwmon/hwmon*/name /sys/class/hwmon/hwmon*/in0_lcrit_alarm 2>&1; cat /sys/class/thermal/thermal_zone0/temp
top -b -n 1 | head -n 15; du -s /data/log/journal; ls -la /data /data/config; md5sum /data/config/*' 2>&1 | mask
  echo "-- host ping $(t)"; ping -c 20 -i 0.5 $B 2>&1 | mask | tail -3; }
push() { # step 2 (no cipher) / 4 (aes128-ctr)
  local step=$1; shift
  h "step $step: host -> board push 30,000,000 B into 'wc -c' $*, beside: board top x4 (5 s), host ping 60 x 0.5 s, ss sampler"; beside
  [ -f $O/net30 ] || head -c 30000000 /dev/urandom > $O/net30
  bash $D/tst008-ss-sample.sh $B 120 > $O/ss$step.txt 2>&1 & local sp=$!
  ssh "${SSHO[@]}" root@$B "top -b -n 4 -d 5 | grep -E 'sshd|CPU:'" > $O/top$step.txt 2>&1 &
  ping -c 60 -i 0.5 $B > $O/ping$step.txt 2>&1 &
  local s0 e0; s0=$(date +%s.%N)
  { time ssh "${SSHO[@]}" "$@" root@$B 'wc -c' < $O/net30 ; } > $O/push$step.txt 2>&1
  e0=$(date +%s.%N)
  echo "-- push: $(tr '\n' ' ' < $O/push$step.txt | mask)"; python3 -c "s=$e0-$s0; print(f'-- push wall {s:.1f} s, {30.0/s:.3f} MB/s (10^6 B)')"
  wait $(jobs -p | grep -v "^$sp$") 2>/dev/null
  echo "-- board top"; mask < $O/top$step.txt; echo "-- host ping under load"; mask < $O/ping$step.txt | tail -3
  wait $sp; echo "== ss during step $step"; cat $O/ss$step.txt; }
pull() { # step 3 (A102: dd | wc -c; counts only if wc prints 30000000; no retry)
  h "step 3 (A102 rerun): board -> host: time ssh <board> 'dd if=/dev/zero bs=1000000 count=30' | wc -c, beside: board top x4 (5 s), host ping 60 x 0.5 s, ss sampler"; beside
  bash $D/tst008-ss-sample.sh $B 120 > $O/ss3.txt 2>&1 & local sp=$!
  ssh "${SSHO[@]}" root@$B "top -b -n 4 -d 5 | grep -E 'sshd|CPU:'" > $O/top3.txt 2>&1 &
  ping -c 60 -i 0.5 $B > $O/ping3.txt 2>&1 &
  local s0 e0; s0=$(date +%s.%N)
  { time ssh "${SSHO[@]}" root@$B 'dd if=/dev/zero bs=1000000 count=30' | wc -c ; } > $O/pull3.txt 2>&1
  e0=$(date +%s.%N)
  echo "-- pull: $(tr '\n' ' ' < $O/pull3.txt | mask)"; python3 -c "s=$e0-$s0; print(f'-- pull wall {s:.1f} s, {30.0/s:.3f} MB/s (10^6 B)')"
  if grep -qx 30000000 $O/pull3.txt; then echo "-- wc -c printed 30000000: counts (A102)"; else echo "-- wc -c did NOT print 30000000: VOID, no retry (A102)"; fi
  wait $(jobs -p | grep -v "^$sp$") 2>/dev/null
  echo "-- board top"; mask < $O/top3.txt; echo "-- host ping under load"; mask < $O/ping3.txt | tail -3
  wait $sp; echo "== ss during step 3"; cat $O/ss3.txt; }
for s in "$@"; do
  case $s in
    1) [ -s $OUT ] || { echo "# bench network read (A96 + A98), bench-op-2, $(date '+%F') EST"; echo "board: $(ssh "${SSHO[@]}" root@$B 'grep meta-wisekiosk /etc/buildinfo; echo uptime $(cut -d" " -f1 /proc/uptime) s; cat /proc/sys/kernel/random/boot_id' 2>&1 | tr '\n' ' ' | mask)"; } >> $OUT
       base 1 >> $OUT ;;
    2) push 2 >> $OUT ;;
    3) pull >> $OUT ;;
    4) push 4 -c aes128-ctr >> $OUT ;;
    5) base 5 >> $OUT ;;
  esac
done
echo "== $(t) steps $* done" >> $OUT
