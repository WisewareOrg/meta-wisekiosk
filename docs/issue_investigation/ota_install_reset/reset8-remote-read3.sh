# read-only: soak timer definition and its start times in boots -2, -1, 0
systemctl cat kiosk-soak.timer 2>&1
echo "== list-timers"; systemctl list-timers --all --no-pager 2>&1 | grep -i soak
for b in -2 -1 0; do
  echo "== boot $b soak starts"
  journalctl -b $b -u kiosk-soak.service --no-pager -o short-iso-precise 2>&1 | grep -E 'Starting|Finished'
done
