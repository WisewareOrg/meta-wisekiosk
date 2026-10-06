# shellcheck shell=bash
# Sourced by kiosk-smoothness-check.sh and kiosk-stability-check.sh, after kiosk-cache.sh,
# with T (ssh target), HERE, KSSH, OUT (the capture), SHOT and WORK set.
#
# settle_dashboard: a pre-run screenshot, retried every 10 s until it is not blank and
# its mean luma (0-255) is at least 10, the rendered dashboard; short of that at 120 s
# is could-not-tell, exit 2.
# KIOSK_PROBE_DEPLOY_FN is shell source sent ahead of a remote script: deploy_probe_conf
# refuses, exit 3, when a kiosk.conf backup from an earlier run is on the board, else
# backs kiosk.conf up and appends KIOSK_PROBE=1.
# restore_conf, once RESTORE_PENDING=1: kiosk.conf from its backup, the probe removed,
# the cache cleared, kiosk restarted. finish, the EXIT trap: restore_conf, then the
# capture to stdout and WORK removed.

settle_dashboard() {
	local wait reply rc mean
	for wait in 0 10 20 30 40 50 60 70 80 90 100 110 120; do
		[ "$wait" -gt 0 ] && { rm -f "$SHOT"; sleep 10; }
		reply=$("$HERE/kiosk-screenshot.sh" "$T" "$SHOT")
		rc=$?
		printf '%s\n' "$reply"
		mean=$(printf '%s\n' "$reply" | sed -n 's/^min=.* mean=\([0-9.]*\)$/\1/p')
		[ $rc -eq 0 ] && awk -v m="${mean:-0}" 'BEGIN { exit !(m >= 10) }' && return 0
		[ "$wait" -eq 120 ] && { echo "could not tell: pre-run screenshot not a rendered dashboard after 120 s (last mean ${mean:-none}, rc $rc)" >&2; exit 2; }
	done
}

# shellcheck disable=SC2016,SC2034  # remote shell source, expanded on the board
KIOSK_PROBE_DEPLOY_FN='deploy_probe_conf() {
	C=/data/config/kiosk.conf
	if [ -e $C.wpe-bak ] || [ -e $C.wpe-absent ]; then
		echo "# REFUSED: a kiosk.conf backup exists -- an earlier run did not restore"; exit 3
	fi
	if [ -f $C ]; then cp -p $C $C.wpe-bak || exit 1; else : > $C.wpe-absent; fi
	[ -s $C ] && [ -n "$(tail -c 1 $C)" ] && echo >> $C
	echo "KIOSK_PROBE=1" >> $C
}'

RESTORE_PENDING=0
restore_conf() {
	[ "$RESTORE_PENDING" = 1 ] || return 0
	RESTORE_PENDING=0
	{ printf '%s\n' "$KIOSK_CACHE_FN"; cat <<'RESTORE'; } | "$KSSH" "$T" 'sh -s' >> "$OUT" 2>&1
C=/data/config/kiosk.conf
if [ -f $C.wpe-bak ]; then mv $C.wpe-bak $C; elif [ -e $C.wpe-absent ]; then rm -f $C $C.wpe-absent; else echo "# NO BACKUP -- kiosk.conf left as found"; fi
rm -f /home/root/kiosk-probe.js
clear_kiosk_cache
systemctl restart kiosk
n=$(grep -c '^KIOSK_PROBE' $C 2>/dev/null)
echo "# restored: kiosk.conf KIOSK_PROBE lines ${n:-none, file absent}, kiosk restarted"
RESTORE
}

# shellcheck disable=SC2317  # runs from the EXIT trap
finish() {
	restore_conf
	cat "$OUT"
	rm -rf "$WORK"
}
