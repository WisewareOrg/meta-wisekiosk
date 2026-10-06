#!/usr/bin/env bash
# Self-test: a kiosk-smoothness-check.sh record never carries the site URL or a
# known identity value in plaintext.
#
#   tools/kiosk-smoothness-check-test.sh
#
# Runs the SHIPPED driver, analyzer and scrub-identity.py, copied byte for byte
# into a throwaway git repository whose tools/kiosk-ssh.sh is a stub device. The
# stub seeds a URL into kiosk.conf, the launcher's argv and its environ, and an
# identity-map value into environ. The record must hold neither, must hold the
# URL's <url sha256:...> tag and the map value's placeholder in their place, and
# must still analyze to rc 0. Two more runs: with no kiosk.conf both kiosk_conf
# fields read `absent` and the record is still rc 0; with a scrub-identity.py
# that refuses (exit 2, as it does without its map), the three redacted fields
# are empty and the record is rc 2.
#
# TO WATCH THIS FAIL -- in a scratch copy of the driver, make safe_fields'
# URL replacement a no-op (replace `text.replace(url, ...)` by `text`) and point
# HERE at it: the URL and URL-tag cases go red. Drop the scrub-identity.py call
# instead (`text` straight to the escaping) and the identity cases go red.
# Ignore the filter's return code and the filter-refuses cases go red; print
# empty kiosk_conf fields for a missing kiosk.conf and the no-kiosk.conf cases do.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
URL='https://seeded-site.example.net/board?park=7&x=1'
SSID=SeededSiteSSID

pass=0
fail=0
check() {
    if [ "$2" = "$3" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $1: want '$3', got '$2'" >&2
    fi
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
repo=$tmp/repo dev=$tmp/dev
mkdir -p "$tmp/home/.config/wisekiosk" "$dev"
git init -q --bare "$tmp/remote.git"
git clone -q "$tmp/remote.git" "$repo" 2> /dev/null
mkdir -p "$repo/tools" "$repo/local"
cp "$HERE/kiosk-smoothness-check.sh" "$HERE/kiosk-framepace.py" "$HERE/scrub-identity.py" "$repo/tools/"

cat > "$repo/tools/kiosk-ssh.sh" << 'EOF'
#!/usr/bin/env bash
# Stub device: answers the driver's commands from $STUB_DEV.
shift
d=$STUB_DEV
case "$*" in
hostname) echo stub-bench ;;
"test -e /tmp/fp.rec && echo stale") ;;
"cat /etc/buildinfo") echo 'meta-wisekiosk    = main:0123456789abcdef0123456789abcdef01234567' ;;
"rauc status --output-format=shell") echo "RAUC_SYSTEM_BOOTED_BOOTNAME='A'" ;;
"test -f /data/config/kiosk.conf && echo present") [ -e "$d/kiosk.conf" ] && echo present ;;
"cat /data/config/kiosk.conf") cat "$d/kiosk.conf" ;;
"for d in"*) printf '101:Xorg\n102:surf\n103:WebKitWebProces\n' ;;
"cat /proc/102/cmdline") cat "$d/cmdline" ;;
"cat /proc/102/environ") cat "$d/environ" ;;
"grep -E 'fb=|mode:' /sys/kernel/debug/dri/0/state") printf '\tfb=96\n\tmode: "1280x720": 60\n' ;;
"systemctl show -p NRestarts --value kiosk.service") echo 0 ;;
"cat /proc/sys/kernel/random/boot_id") echo stub-boot ;;
"cut -d' ' -f1 /proc/uptime") echo 100.5 ;;
"kiosk-framepace --seconds 1 --out /tmp/fp.rec") ;;
"cat /tmp/fp.rec") cat "$d/fp.rec" ;;
"kiosk-drmgrab /tmp/fp.ppm") ;;
"cat /tmp/fp.ppm") printf 'P6\n1 1\n255\nabc' ;;
"rm -f /tmp/fp.rec" | "rm -f /tmp/fp.ppm") ;;
*) echo "stub: unhandled: $*" >&2; exit 99 ;;
esac
EOF
chmod +x "$repo/tools/"*
echo 'local/' > "$repo/.gitignore"
git -C "$repo" add -A
git -C "$repo" -c core.hooksPath=/dev/null -c user.name=t -c user.email=t@t commit -qm stub
git -C "$repo" push -q origin HEAD 2> /dev/null
git -C "$repo" branch -q --set-upstream-to="origin/$(git -C "$repo" branch --show-current)"
fence='```'
printf '%sidentity\nbench.hostname = stub-bench\nwifi.ssid = %s\n%s\n' "$fence" "$SSID" "$fence" \
    > "$repo/local/device-identity.md"
echo "PIPELINE_LOCK=\"$tmp/lock\"" > "$tmp/home/.config/wisekiosk/pipeline.env"

printf 'KIOSK_URL=%s\nKIOSK_INSPECTOR=0\n' "$URL" > "$dev/kiosk.conf"
printf 'surf\0-K\0%s\0' "$URL" > "$dev/cmdline"
printf 'HOME=/root\0KIOSK_URL=%s\0NOTE=%s\0' "$URL" "$SSID" > "$dev/environ"
{
    printf 'H tool=0123456789ab\nH mode=1280x720@60\nH pacing=vblank\n'
    printf 'H regions=x70-325,434-688;y303,326,350,388,411,522,545,568,607,630;step1\n'
    printf 'H start=2026-01-01T00:00:00Z\nH seconds=1\n'
    for i in $(seq 0 60); do printf 'S %d 96 %016x %d\n' $((i * 16666667)) $((i % 2)) "$i"; done
    printf 'H cpu_ms=5\nH samples=61 missed=0 end=2026-01-01T00:00:01Z\n'
} > "$dev/fp.rec"

# run_driver <name> <expected-rc>: one driver run; sets $rec to its record.
run_driver() {
    rm -rf "$repo/local/framepace"
    HOME="$tmp/home" STUB_DEV="$dev" "$repo/tools/kiosk-smoothness-check.sh" root@stub 1 > "$tmp/out" 2>&1
    check "$1: driver rc" "$?" "$2"
    rec=$(find "$repo/local/framepace" -name '*.rec' 2> /dev/null | head -1)
    check "$1: a record was written" "$([ -s "$rec" ] && echo yes)" yes
}

run_driver "seeded run" 0

url_tag="<url sha256:$(printf '%s' "$URL" | sha256sum | cut -d' ' -f1)>"
check "the URL is nowhere in the record" "$(grep -cF "$URL" "$rec")" 0
check "the URL's host is nowhere in the record" "$(grep -cF seeded-site.example.net "$rec")" 0
check "the identity value is nowhere in the record" "$(grep -ciF "$SSID" "$rec")" 0
check "kiosk_conf carries the URL tag" "$(grep '^P kiosk_conf=' "$rec" | grep -cF "$url_tag")" 1
check "proc_cmdline_surf carries the URL tag" "$(grep '^P proc_cmdline_surf=' "$rec" | grep -cF "$url_tag")" 1
check "proc_environ_surf carries the URL tag" "$(grep '^P proc_environ_surf=' "$rec" | grep -cF "$url_tag")" 1
check "proc_environ_surf carries the identity placeholder" \
    "$(grep '^P proc_environ_surf=' "$rec" | grep -cF '<wifi.ssid>')" 1
check "kiosk_conf carries the raw sha256" \
    "$(grep -cF "P kiosk_conf=sha256:$(sha256sum < "$dev/kiosk.conf" | cut -d' ' -f1) " "$rec")" 1

mv "$dev/kiosk.conf" "$dev/kiosk.conf.off"
run_driver "no kiosk.conf" 0
check "no kiosk.conf: kiosk_conf_sha256 is absent" "$(grep -cx 'P kiosk_conf_sha256=absent' "$rec")" 1
check "no kiosk.conf: kiosk_conf is absent" "$(grep -cx 'P kiosk_conf=absent' "$rec")" 1
mv "$dev/kiosk.conf.off" "$dev/kiosk.conf"

printf '#!/bin/sh\nexit 2\n' > "$repo/tools/scrub-identity.py"
git -C "$repo" -c core.hooksPath=/dev/null -c user.name=t -c user.email=t@t commit -qam refuse
git -C "$repo" push -q origin HEAD 2> /dev/null
run_driver "filter refuses" 2
for key in kiosk_conf proc_cmdline_surf proc_environ_surf; do
    check "filter refuses: $key is empty" "$(grep -cx "P $key=" "$rec")" 1
done

[ "$fail" -eq 0 ] || cat "$tmp/out" >&2
echo "pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
