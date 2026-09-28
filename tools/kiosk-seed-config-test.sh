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

# A PATH holding only `busybox --list`'s applets on bench (W7, BusyBox
# v1.36.1), verbatim -- not every command on the target (a separate setuid
# busybox.suid provides more, e.g. ping, none of it needed by this script),
# and not the dev host's own coreutils. Neither `install` nor `timeout` is on
# this list. The host's own `install` on the earlier, unrestricted PATH is
# why the seed cases above never caught this -- the fix must work with only
# what this list provides, plus bash/sh to run the script itself.
BUSYBOX_APPLETS='[ [[ addgroup adduser ascii ash awk base32 basename blkid bunzip2 bzcat bzip2 cat
chattr chgrp chmod chown chroot chvt clear cmp cp cpio crc32 cut date dc dd deallocvt delgroup
deluser depmod df diff dirname dmesg dnsdomainname du dumpkmap dumpleases echo egrep env expr false
fbset fdisk fgrep find flock free fsck fstrim fuser getopt getty grep groups gunzip gzip head
hexdump hostname hwclock id ifconfig ifdown ifup insmod ip kill killall klogd less ln loadfont
loadkmap logger logname logread losetup ls lsmod lzcat md5sum mesg microcom mkdir mkfifo mknod
mkswap mktemp modprobe more mount mountpoint mv nc netstat nohup nproc nslookup od openvt patch
pgrep pidof pivot_root printf ps pwd rdate readlink realpath reboot renice reset resize rev rfkill
rm rmdir rmmod route run-parts sed seq setconsole setsid sh sha1sum sha256sum shuf sleep sort
start-stop-daemon stat strings stty sulogin swapoff swapon switch_root sync sysctl syslogd tail tar
tee telnet test tftp time top touch tr true ts tty udhcpc udhcpd umount uname uniq unlink unzip
uptime users usleep vi watch wc wget which who whoami xargs xzcat yes zcat'

BINDIR="$TOP/bin"
mkdir -p "$BINDIR"
for name in $BUSYBOX_APPLETS bash; do
    resolved=$(type -P "$name" 2>/dev/null) || continue
    ln -sf "$resolved" "$BINDIR/$name"
done

# --- absent: seeded byte-equal to the image default, mode 0644 -----------
A="$TOP/a"
mkdir -p "$A/usr/share/wisekiosk"
printf '{"fixture":"a default config, not a real site value"}' \
    > "$A/usr/share/wisekiosk/config.example.json"

out=$(ROOT="$A" "$SCRIPT" 2>&1); rc=$?
target="$A/data/config/config.json"
source="$A/usr/share/wisekiosk/config.example.json"

if [ "$rc" -eq 0 ]; then
    ok "absent: exits 0"
else
    bad "absent: exits 0" "rc=$rc"
fi
if [ -e "$target" ] && cmp -s "$target" "$source"; then
    ok "absent: seeded byte-equal to the image default"
else
    bad "absent: seeded byte-equal to the image default" \
        "target $([ -e "$target" ] && echo present || echo MISSING)"
fi
mode=$(stat -c '%a' "$target" 2>/dev/null || echo "?")
if [ "$mode" = "644" ]; then
    ok "absent: seeded file is mode 0644"
else
    bad "absent: seeded file is mode 0644" "got mode=$mode"
fi
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

if [ "$rc" -eq 0 ]; then
    ok "present, non-empty: exits 0"
else
    bad "present, non-empty: exits 0" "rc=$rc"
fi
if [ "$before" = "$after" ]; then
    ok "present, non-empty: byte-unchanged"
else
    bad "present, non-empty: byte-unchanged" "checksum changed"
fi

# --- present, empty: byte-unchanged (still zero bytes) --------------------
C="$TOP/c"
mkdir -p "$C/usr/share/wisekiosk" "$C/data/config"
printf '{"fixture":"a default that must not be applied either"}' \
    > "$C/usr/share/wisekiosk/config.example.json"
: > "$C/data/config/config.json"

ROOT="$C" "$SCRIPT" >/dev/null 2>&1; rc=$?
size=$(stat -c '%s' "$C/data/config/config.json" 2>/dev/null || echo "?")

if [ "$rc" -eq 0 ]; then
    ok "present, empty: exits 0"
else
    bad "present, empty: exits 0" "rc=$rc"
fi
if [ "$size" = "0" ]; then
    ok "present, empty: byte-unchanged (still empty)"
else
    bad "present, empty: byte-unchanged (still empty)" "size=$size"
fi

# --- source missing: no config.json created, exact log line --------------
D="$TOP/d"
mkdir -p "$D/usr/share/wisekiosk"

out=$(ROOT="$D" "$SCRIPT" 2>&1); rc=$?

if [ "$rc" -eq 0 ]; then
    ok "source missing: exits 0"
else
    bad "source missing: exits 0" "rc=$rc"
fi
if [ -e "$D/data/config/config.json" ]; then
    bad "source missing: no config.json created" "file exists"
else
    ok "source missing: no config.json created"
fi
if [ -d "$D/data/config" ]; then
    ok "source missing: /data/config still created"
else
    bad "source missing: /data/config still created" "directory absent"
fi
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

if [ "$rc" -eq 0 ]; then
    ok "empty source: exits 0"
else
    bad "empty source: exits 0" "rc=$rc"
fi
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

# --- write failure: /data/config exists but is not writable ---------------
# `mkdir -p` on an already-existing directory never needs write permission
# on it, so this reaches the actual copy/move -- which does, and fails.
# W7's real-device finding: with no `set -e`, a failed copy fell through to
# the success log line and exit 0 regardless. A crash or a full /data must
# not read as success, so this asserts the honest outcome: no config.json,
# no leftover .tmp, no false "seeded" claim, a stated failure, still exit 0.
F="$TOP/f"
mkdir -p "$F/usr/share/wisekiosk" "$F/data/config"
printf '{"fixture":"a default config, not a real site value"}' \
    > "$F/usr/share/wisekiosk/config.example.json"
chmod 0500 "$F/data/config"

out=$(ROOT="$F" "$SCRIPT" 2>&1); rc=$?
chmod 0700 "$F/data/config"

if [ "$rc" -eq 0 ]; then
    ok "write failure: exits 0"
else
    bad "write failure: exits 0" "rc=$rc"
fi
if [ -e "$F/data/config/config.json" ]; then
    bad "write failure: no config.json created" "file exists"
else
    ok "write failure: no config.json created"
fi
if [ -e "$F/data/config/config.json.tmp" ]; then
    bad "write failure: no config.json.tmp left behind" "tmp artifact still present"
else
    ok "write failure: no config.json.tmp left behind"
fi
case "$out" in
    *"seeded /data/config/config.json"*)
        bad "write failure: log does not falsely claim success" "output: $out" ;;
    *) ok "write failure: log does not falsely claim success" ;;
esac
case "$out" in
    *[Ff]ail*|*"could not"*|*"not written"*|*[Ee]rror*)
        ok "write failure: log states the failure" ;;
    *) bad "write failure: log states the failure" "output: $out" ;;
esac

# --- busybox PATH, absent: install is not a busybox applet on the target --
# The same "absent" scenario as the very first case above, run with only the
# device's own command set on PATH -- `install` (and `timeout`) are missing
# there. Against the unfixed script this must fail: that gap is the actual
# W7 finding, invisible on a dev host whose own coreutils `install` papers
# over it.
G="$TOP/g"
mkdir -p "$G/usr/share/wisekiosk"
printf '{"fixture":"a default config, not a real site value"}' \
    > "$G/usr/share/wisekiosk/config.example.json"

out=$(env -i PATH="$BINDIR" ROOT="$G" "$BINDIR/sh" "$SCRIPT" 2>&1); rc=$?
target="$G/data/config/config.json"
source="$G/usr/share/wisekiosk/config.example.json"

if [ "$rc" -eq 0 ]; then
    ok "busybox PATH, absent: exits 0"
else
    bad "busybox PATH, absent: exits 0" "rc=$rc"
fi
if [ -e "$target" ] && cmp -s "$target" "$source"; then
    ok "busybox PATH, absent: seeded byte-equal to the image default"
else
    bad "busybox PATH, absent: seeded byte-equal to the image default" \
        "target $([ -e "$target" ] && echo present || echo MISSING) -- install is not a busybox applet"
fi
case "$out" in
    *"seeded /data/config/config.json"*)
        if [ -e "$target" ]; then
            ok "busybox PATH, absent: the 'seeded' claim matches reality"
        else
            bad "busybox PATH, absent: the 'seeded' claim matches reality" \
                "logged success with no file ever written -- output: $out"
        fi
        ;;
    *) ok "busybox PATH, absent: does not falsely claim success" ;;
esac
if [ -e "$G/data/config/config.json.tmp" ]; then
    bad "busybox PATH, absent: no config.json.tmp left behind" "tmp artifact still present"
else
    ok "busybox PATH, absent: no config.json.tmp left behind"
fi

echo
printf 'pass=%s fail=%s\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
