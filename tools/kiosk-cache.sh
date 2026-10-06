# shellcheck shell=bash
# Sourced by kiosk-smoothness-check.sh and kiosk-stability-check.sh. KIOSK_CACHE_FN is shell
# source sent ahead of a remote script: kiosk_cache_dir prints WebKit's network-session cache
# dir, <XDG_CACHE_HOME, else HOME/.cache, of the running wpe-kiosk, else uid 0's passwd
# home/.cache>/wpe; clear_kiosk_cache removes it and prints "# cleared <dir> (<n> entries)" or
# "# no cache dir found (<dir>)". require_kiosk_cache <kiosk-ssh> <target>, run on the host
# before anything is deployed: could-not-tell, exit 2, unless that dir exists on the board and
# holds at least one entry.
# shellcheck disable=SC2016,SC2034  # remote shell source, expanded on the board
KIOSK_CACHE_FN='kiosk_cache_dir() {
	p=$(pidof wpe-kiosk | cut -d" " -f1)
	e=""
	[ -n "$p" ] && e=$(tr "\0" "\n" < /proc/$p/environ)
	x=$(printf "%s\n" "$e" | sed -n "s/^XDG_CACHE_HOME=//p")
	h=$(printf "%s\n" "$e" | sed -n "s/^HOME=//p")
	[ -n "$h" ] || h=$(awk -F: "\$3 == 0 { print \$6; exit }" /etc/passwd)
	echo "${x:-$h/.cache}/wpe"
}
clear_kiosk_cache() {
	c=$(kiosk_cache_dir)
	if [ -d "$c" ]; then
		n=$(find "$c" | wc -l)
		rm -rf "$c"
		echo "# cleared $c ($((n - 1)) entries)"
	else
		echo "# no cache dir found ($c)"
	fi
}'

require_kiosk_cache() {
	local r
	# shellcheck disable=SC2016  # remote shell source, expanded on the board
	r=$( { printf '%s\n' "$KIOSK_CACHE_FN"
		echo 'c=$(kiosk_cache_dir); n=0; [ -d "$c" ] && n=$(($(find "$c" | wc -l) - 1)); echo "$n $c"'
	} | "$1" "$2" 'sh -s' | tail -n 1)
	case "$r" in
	"") echo "could not tell: no answer from $2 to the cache check" >&2; exit 2 ;;
	"0 "*) echo "could not tell: wpe-kiosk cache ${r#* } absent or empty before the first restart" >&2; exit 2 ;;
	esac
}
