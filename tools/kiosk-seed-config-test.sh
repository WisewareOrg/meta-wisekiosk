#!/usr/bin/env bash
# Self-test for meta-wisekiosk/recipes-core/kiosk-provision/files/kiosk-seed-config.
# Run by `just guards` and by CI.
#
# The script seeds /data/config/config.json from the image's shipped default
# ONLY the first time -- a device that already has one (however it got there,
# including an empty file) must come back byte-for-byte unchanged, or an
# operator's edit is silently clobbered on the next boot.
#
# Every case runs against a fabricated ROOT, never /data or /usr on this host:
# the script honours ROOT on its paths so this can run as a normal user and in
# CI, with no root and no real device. Fixtures carry no site value -- this
# repository is PUBLIC.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../meta-wisekiosk/recipes-core/kiosk-provision/files/kiosk-seed-config"

TOP=$(mktemp -d)
trap 'rm -rf "$TOP"' EXIT

pass=0; fail=0
ok()  { printf 'ok    %s\n' "$1"; pass=$((pass+1)); }
bad() { printf 'FAIL  %s\n' "$1"; [ $# -gt 1 ] && printf '        %s\n' "$2"; fail=$((fail+1)); }

# --- absent: seeded byte-equal to the image default, mode 0644 -----------
A="$TOP/a"
mkdir -p "$A/usr/share/wisekiosk"
printf '{"fixture":"a default config, not a real site value"}' \
    > "$A/usr/share/wisekiosk/config.example.json"

out=$(ROOT="$A" "$SCRIPT" 2>&1); rc=$?
target="$A/data/config/config.json"
source="$A/usr/share/wisekiosk/config.example.json"

[ "$rc" -eq 0 ] && ok "absent: exits 0" || bad "absent: exits 0" "rc=$rc"
if [ -e "$target" ] && cmp -s "$target" "$source"; then
    ok "absent: seeded byte-equal to the image default"
else
    bad "absent: seeded byte-equal to the image default" \
        "target $([ -e "$target" ] && echo present || echo MISSING)"
fi
mode=$(stat -c '%a' "$target" 2>/dev/null || echo "?")
[ "$mode" = "644" ] && ok "absent: seeded file is mode 0644" \
    || bad "absent: seeded file is mode 0644" "got mode=$mode"
case "$out" in
    *"seeded /data/config/config.json from the image default"*)
        ok "absent: logs the seed line" ;;
    *) bad "absent: logs the seed line" "output: $out" ;;
esac
if [ -e "$A/data/config/config.json.tmp" ]; then
    bad "absent: no config.json.tmp left behind" "tmp artifact still present"
else
    ok "absent: no config.json.tmp left behind"
fi

# --- present, non-empty: byte-unchanged -----------------------------------
B="$TOP/b"
mkdir -p "$B/usr/share/wisekiosk" "$B/data/config"
printf '{"fixture":"a different default, must not be applied"}' \
    > "$B/usr/share/wisekiosk/config.example.json"
printf 'PRESENT_NONEMPTY_SENTINEL' > "$B/data/config/config.json"
before=$(cksum "$B/data/config/config.json")

ROOT="$B" "$SCRIPT" >/dev/null 2>&1; rc=$?
after=$(cksum "$B/data/config/config.json")

[ "$rc" -eq 0 ] && ok "present, non-empty: exits 0" \
    || bad "present, non-empty: exits 0" "rc=$rc"
[ "$before" = "$after" ] && ok "present, non-empty: byte-unchanged" \
    || bad "present, non-empty: byte-unchanged" "checksum changed"

# --- present, empty: byte-unchanged (still zero bytes) --------------------
C="$TOP/c"
mkdir -p "$C/usr/share/wisekiosk" "$C/data/config"
printf '{"fixture":"a default that must not be applied either"}' \
    > "$C/usr/share/wisekiosk/config.example.json"
: > "$C/data/config/config.json"

ROOT="$C" "$SCRIPT" >/dev/null 2>&1; rc=$?
size=$(stat -c '%s' "$C/data/config/config.json" 2>/dev/null || echo "?")

[ "$rc" -eq 0 ] && ok "present, empty: exits 0" \
    || bad "present, empty: exits 0" "rc=$rc"
[ "$size" = "0" ] && ok "present, empty: byte-unchanged (still empty)" \
    || bad "present, empty: byte-unchanged (still empty)" "size=$size"

# --- source missing: no config.json created, exact log line --------------
D="$TOP/d"
mkdir -p "$D/usr/share/wisekiosk"

out=$(ROOT="$D" "$SCRIPT" 2>&1); rc=$?

[ "$rc" -eq 0 ] && ok "source missing: exits 0" \
    || bad "source missing: exits 0" "rc=$rc"
if [ -e "$D/data/config/config.json" ]; then
    bad "source missing: no config.json created" "file exists"
else
    ok "source missing: no config.json created"
fi
[ -d "$D/data/config" ] && ok "source missing: /data/config still created" \
    || bad "source missing: /data/config still created" "directory absent"
case "$out" in
    *"no image default config to seed"*)
        ok "source missing: logs the exact no-source line" ;;
    *) bad "source missing: logs the exact no-source line" "output: $out" ;;
esac

# --- source exists but empty: same as missing (the -s check, not just -e) -
E="$TOP/e"
mkdir -p "$E/usr/share/wisekiosk"
: > "$E/usr/share/wisekiosk/config.example.json"

out=$(ROOT="$E" "$SCRIPT" 2>&1); rc=$?

[ "$rc" -eq 0 ] && ok "empty source: exits 0" \
    || bad "empty source: exits 0" "rc=$rc"
if [ -e "$E/data/config/config.json" ]; then
    bad "empty source: no config.json created" "file exists"
else
    ok "empty source: no config.json created"
fi
case "$out" in
    *"no image default config to seed"*)
        ok "empty source: logs the exact no-source line" ;;
    *) bad "empty source: logs the exact no-source line" "output: $out" ;;
esac

echo
printf 'pass=%s fail=%s\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
