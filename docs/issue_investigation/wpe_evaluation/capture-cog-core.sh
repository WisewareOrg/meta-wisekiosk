#!/bin/bash
# capture-cog-core.sh <out-dir> -- collect a core from cog's SIGSEGV on stop, on the board at
# $BENCH (ssh target).
#
# The kernel discards cores (core_pattern |/bin/false) and kiosk.service's soft core limit is 0,
# so the core goes to a pipe handler, which the limit does not gate: /data/cog-core/dump.sh
# writes /data/cog-core/core.<comm>.<pid>. Before the restart it records /etc/buildinfo, cog's
# identity (/proc/<pid>/exe build-id via readelf when the image has it, else its md5sum), cog's
# limits and the original core_pattern. `systemctl restart kiosk` stops cog, which dumps; the
# core and the system journal since the restart are fetched into <out-dir>. core_pattern is
# restored and /data/cog-core removed on any exit once armed. An existing /data/cog-core means an
# earlier run did not clean up: refused, exit 2, nothing touched.
set -u
T=${BENCH:?ssh target, e.g. root@<bench>}
OUT=${1:?out-dir}
HERE=$(dirname "$(readlink -f "$0")")
KSSH=$(git -C "$HERE" rev-parse --show-toplevel)/tools/kiosk-ssh.sh
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite a capture" >&2; exit 2; }
mkdir -p "$OUT"

"$KSSH" "$T" 'sh -s' > "$OUT/pre.txt" 2>&1 <<'PRE'
[ -e /data/cog-core ] && { echo "REFUSED: /data/cog-core exists"; exit 3; }
p=$(pidof cog)
[ -n "$p" ] || { echo "REFUSED: no cog running"; exit 3; }
echo "pid $p"
if command -v readelf > /dev/null 2>&1; then
	echo "cog-id build-id $(readelf -n /proc/$p/exe | sed -n 's/.*Build ID: *//p')"
else
	echo "cog-id md5 $(md5sum < /proc/$p/exe | cut -d' ' -f1)"
fi
echo "core_pattern $(cat /proc/sys/kernel/core_pattern)"
grep -i 'core' /proc/$p/limits
df -k /data | tail -n 1
PRE
rc=$?
[ $rc -eq 0 ] || { echo "pre-check failed (rc $rc): $(cat "$OUT/pre.txt")" >&2; exit 2; }
"$KSSH" "$T" 'cat /etc/buildinfo' > "$OUT/buildinfo.txt" || { echo "could not read /etc/buildinfo" >&2; exit 2; }
sed -n 's/^cog-id //p' "$OUT/pre.txt" > "$OUT/cog-id.txt"
ORIG=$(sed -n 's/^core_pattern //p' "$OUT/pre.txt")
[ -n "$ORIG" ] || { echo "could not read core_pattern" >&2; exit 2; }

ARMED=0
restore() {
	[ "$ARMED" = 1 ] || return 0
	ARMED=0
	"$KSSH" "$T" "printf '%s\n' '$ORIG' > /proc/sys/kernel/core_pattern; rm -rf /data/cog-core; echo \"restored core_pattern \$(cat /proc/sys/kernel/core_pattern)\"" \
		>> "$OUT/restore.txt" 2>&1
}
trap restore EXIT
trap 'exit 1' INT TERM HUP

ARMED=1
"$KSSH" "$T" 'sh -s' > "$OUT/arm.txt" 2>&1 <<'ARM'
mkdir /data/cog-core || exit 1
printf '#!/bin/sh\ncat > /data/cog-core/core.$1.$2\n' > /data/cog-core/dump.sh
chmod 755 /data/cog-core/dump.sh
echo '|/data/cog-core/dump.sh %e %p' > /proc/sys/kernel/core_pattern
echo "armed core_pattern $(cat /proc/sys/kernel/core_pattern)"
S=$(date +%s)
echo "restart-epoch $S"
systemctl restart kiosk
i=0
last=-1
while [ $i -lt 60 ]; do
	sleep 1
	f=$(ls /data/cog-core/core.* 2>/dev/null | head -n 1)
	if [ -n "$f" ]; then
		n=$(wc -c < "$f")
		[ "$n" -gt 0 ] && [ "$n" = "$last" ] && break
		last=$n
	fi
	i=$((i + 1))
done
ls -l /data/cog-core/
journalctl -b --since @$S --no-pager > /data/cog-core/journal.txt 2>&1
ARM
rc=$?
[ $rc -eq 0 ] || { echo "arm/restart failed (rc $rc), see $OUT/arm.txt" >&2; exit 1; }

"$KSSH" "$T" 'cat /data/cog-core/journal.txt' > "$OUT/journal.txt"
CORE=$("$KSSH" "$T" 'ls /data/cog-core/' | grep '^core\.' | head -n 1)
if [ -z "$CORE" ]; then
	echo "no core written -- see $OUT/arm.txt and $OUT/journal.txt" >&2
	exit 1
fi
"$KSSH" "$T" "cat /data/cog-core/$CORE" > "$OUT/$CORE" || { echo "core fetch failed" >&2; exit 1; }
want=$("$KSSH" "$T" "wc -c < /data/cog-core/$CORE")
[ "$(wc -c < "$OUT/$CORE")" = "$want" ] || { echo "core fetch truncated: want $want bytes" >&2; exit 1; }
echo "captured $OUT/$CORE ($(wc -c < "$OUT/$CORE") bytes)"
