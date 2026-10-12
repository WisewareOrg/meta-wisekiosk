#!/bin/bash
# Re-run of docs/issue_investigation/wpe_evaluation/run-time-to-page.sh (09b36c2) with READ_AT=300
# instead of the script's hardcoded 115. Same deployed time-to-page.js beacon and the SAME
# committed time-to-page-x.sh (which already takes READ_AT as $1) -- only the CLI arg differs.
# Per main's ruling on #185 (in-scope engineering): the wait doesn't perturb the boot.
set -u
HERE=/home/tjwise/meta-wisekiosk-185-ttp/docs/issue_investigation/wpe_evaluation
T='root@<BENCH_ADDRESS>'
OUT=${1:?out}
KSSH=/home/tjwise/meta-wisekiosk-185-ttp/tools/kiosk-ssh.sh
JS=/home/tjwise/meta-wisekiosk-185-ttp/meta-wisekiosk/recipes-core/kiosk-bootprof/files/time-to-page.js
[ -e "$OUT" ] && { echo "$OUT exists -- refusing to overwrite" >&2; exit 2; }

{
echo "# run-ttp-readat300.sh (manual re-run of run-time-to-page.sh@09b36c2, READ_AT=300) role=bench boots=3 wait=120 READ_AT=300"
echo "# time-to-page.js sha256 $(sha256sum < "$JS" | cut -d' ' -f1)"
} > "$OUT"
"$KSSH" "$T" 'cat > /home/root/.surf/script.js' < "$JS" || exit 1
"$KSSH" "$T" "cat > /data/time-to-page-x.sh" < "$HERE/time-to-page-x.sh" || exit 1

boot() {
	echo "=== boot $1: reboot at $(date -u +%FT%TZ) ===" >> "$OUT"
	"$KSSH" "$T" 'systemctl reboot' >> "$OUT" 2>&1
	"$KSSH" "$T" --close > /dev/null 2>&1
	sleep 120
	"$KSSH" "$T" 'sh -s' 2>&1 <<'REMOTE' | tee -a "$OUT"
echo "# buildinfo $(grep '^meta-wisekiosk ' /etc/buildinfo)"
echo "# $(rauc status 2>&1 | grep 'Booted from')"
sh /data/time-to-page-x.sh 300
REMOTE
	"$KSSH" "$T" --close > /dev/null 2>&1
}

for i in 1 2 3; do
	case "$(boot "$i")" in
	*SUSPECT*) boot "$i-rerun" > /dev/null ;;
	esac
done

"$KSSH" "$T" ': > /home/root/.surf/script.js; rm -f /data/time-to-page-x.sh' >> "$OUT" 2>&1
echo "# complete $(date -u +%FT%TZ)" >> "$OUT"
