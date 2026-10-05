# shellcheck shell=bash
# Sourced by the wpe_evaluation drivers. COG_CACHE_FN is shell source sent ahead of a remote
# script: cog_cache_dir prints WebKit's network-session cache dir, <XDG_CACHE_HOME, else
# HOME/.cache, of the running cog, else uid 0's passwd home/.cache>/wpe; clear_cog_cache removes
# it and prints "# cleared <dir> (<n> entries)" or "# no cache dir found (<dir>)".
# shellcheck disable=SC2016,SC2034  # remote shell source, expanded on the board
COG_CACHE_FN='cog_cache_dir() {
	p=$(pidof cog | cut -d" " -f1)
	e=""
	[ -n "$p" ] && e=$(tr "\0" "\n" < /proc/$p/environ)
	x=$(printf "%s\n" "$e" | sed -n "s/^XDG_CACHE_HOME=//p")
	h=$(printf "%s\n" "$e" | sed -n "s/^HOME=//p")
	[ -n "$h" ] || h=$(awk -F: "\$3 == 0 { print \$6; exit }" /etc/passwd)
	echo "${x:-$h/.cache}/wpe"
}
clear_cog_cache() {
	c=$(cog_cache_dir)
	if [ -d "$c" ]; then
		n=$(find "$c" | wc -l)
		rm -rf "$c"
		echo "# cleared $c ($((n - 1)) entries)"
	else
		echo "# no cache dir found ($c)"
	fi
}'
