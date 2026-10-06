#!/usr/bin/env bash
# One frame-pacing record of the kiosk page: provenance, a kiosk-framepace run,
# a closing screenshot, and the analyzer's metrics, in one file.
#
#   tools/kiosk-smoothness-check.sh root@<host> [seconds=600]
#
# Writes local/framepace/<UTC stamp>-<role>-<engine>.rec and the end-of-run
# kiosk-drmgrab frame beside it as .ppm, then exits with
# tools/kiosk-framepace.py's rc: 0 metrics given, 2 could not tell. Exit 2 with
# no record when the checkout is dirty or not at its upstream, the board lock is
# held, the hostname matches no role in local/device-identity.md, or a stale
# /tmp/fp.rec is on the device.
#
# The board lock is the pipeline's PIPELINE_LOCK, read from
# ~/.config/wisekiosk/pipeline.env and held for the whole run.
#
# Read-only on the device apart from /tmp/fp.rec and /tmp/fp.ppm, both removed
# once fetched.
set -uo pipefail

PIPELINE_ENV="$HOME/.config/wisekiosk/pipeline.env"
REMOTE_REC=/tmp/fp.rec
REMOTE_PPM=/tmp/fp.ppm

usage() {
    echo "usage: kiosk-smoothness-check.sh <ssh-target> [seconds=600]" >&2
    echo "board lock: PIPELINE_LOCK from $PIPELINE_ENV" >&2
    exit 2
}
refuse() { echo "kiosk-smoothness-check.sh: $*" >&2; exit 2; }

if [ $# -lt 1 ] || [ $# -gt 2 ]; then usage; fi
HOST=$1
DURATION=${2:-600}
[[ $DURATION =~ ^[1-9][0-9]*$ ]] || usage

cd "$(dirname "$0")/.." || exit 2

[ -z "$(git status --porcelain)" ] || refuse "the checkout is not clean"
head=$(git rev-parse HEAD)
upstream=$(git rev-parse '@{upstream}' 2> /dev/null) || refuse "HEAD has no upstream"
[ "$head" = "$upstream" ] || refuse "HEAD $head is not its upstream $upstream"

[ -f "$PIPELINE_ENV" ] || refuse "$PIPELINE_ENV not found: no board lock to take"
# shellcheck disable=SC1090
lock=$(. "$PIPELINE_ENV" && printf '%s' "${PIPELINE_LOCK:-}")
[ -n "$lock" ] || refuse "PIPELINE_LOCK is not set in $PIPELINE_ENV"
exec 9> "$lock" || refuse "cannot open the board lock $lock"
flock -n 9 || refuse "the board lock $lock is held"

dev() { tools/kiosk-ssh.sh "$HOST" "$@"; }

# The value of an identity key in local/device-identity.md's identity block.
identity() {
    awk -v k="$1" '/^```identity/ { f = 1; next } /^```/ { f = 0 }
        f && $1 == k && $2 == "=" { sub(/^[^=]*=[ \t]*/, ""); print; exit }' local/device-identity.md 2> /dev/null
}

hostname=$(dev hostname)
if [ -n "$hostname" ] && [ "$hostname" = "$(identity bench.hostname)" ]; then
    role=bench
elif [ -n "$hostname" ] && [ "$hostname" = "$(identity public.prod.hostname)" ]; then
    role=prod
else
    refuse "hostname '$hostname' matches no role in local/device-identity.md"
fi
[ "$(dev "test -e $REMOTE_REC && echo stale")" != stale ] || refuse "$REMOTE_REC already exists on the device"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
P=()
p() { P+=("P $1=$2"); }

stamp=$(date -u +%Y%m%dT%H%M%SZ)
p tools_commit "$head"
p host_role "$role"
p buildinfo_wisekiosk "$(dev cat /etc/buildinfo | awk '$1 == "meta-wisekiosk" { print; exit }')"
p slot "$(dev rauc status --output-format=shell | sed -n "s/^RAUC_SYSTEM_BOOTED_BOOTNAME='\(.*\)'/\1/p")"
if [ "$(dev "test -f /data/config/kiosk.conf && echo present")" = present ]; then
    dev cat /data/config/kiosk.conf > "$tmp/kiosk.conf"
    p kiosk_conf_sha256 "$(sha256sum < "$tmp/kiosk.conf" | cut -d' ' -f1)"
    p kiosk_conf "$(base64 -w0 < "$tmp/kiosk.conf")"
else
    p kiosk_conf_sha256 absent
    p kiosk_conf absent
fi

# shellcheck disable=SC2016
procs=$(dev 'for d in /proc/[0-9]*; do c=$(cat "$d/comm" 2> /dev/null) || continue
    case $c in Xorg|surf|WebKitWebProces|WebKitNetworkPr|wpe-kiosk|WPE*) echo "${d#/proc/}:$c";; esac
    done' | sort -n)
p browser_procs "$(paste -sd, <<< "$procs")"
comms=$(cut -d: -f2 <<< "$procs")
has_x=$(grep -cx Xorg <<< "$comms")
has_wpe=$(grep -cx wpe-kiosk <<< "$comms")
engine=unknown launcher=
if [ "$has_x" -gt 0 ] && [ "$has_wpe" -eq 0 ]; then
    engine=X launcher=surf
elif [ "$has_wpe" -gt 0 ] && [ "$has_x" -eq 0 ]; then
    engine=WPE launcher=wpe-kiosk
fi
if [ -n "$launcher" ]; then
    pid=$(awk -F: -v c="$launcher" '$2 == c { print $1; exit }' <<< "$procs")
    if [ -n "$pid" ]; then
        p "proc_cmdline_$launcher" "$(dev cat "/proc/$pid/cmdline" | base64 -w0)"
        p "proc_environ_$launcher" "$(dev cat "/proc/$pid/environ" | base64 -w0)"
    fi
fi

p crtc_state "$(dev grep -E "'fb=|mode:'" /sys/kernel/debug/dri/0/state |
    awk 'NR > 1 { printf " | " } { printf "%s", $0 }')"
p kiosk_nrestarts_start "$(dev systemctl show -p NRestarts --value kiosk.service)"
p boot_id "$(dev cat /proc/sys/kernel/random/boot_id)"
uptime=$(dev "cut -d' ' -f1 /proc/uptime")
p uptime_s "${uptime%%.*}"

dev kiosk-framepace --seconds "$DURATION" --out "$REMOTE_REC"
echo "kiosk-framepace rc=$?" >&2
dev cat "$REMOTE_REC" > "$tmp/fp.rec"
dev rm -f "$REMOTE_REC"

p kiosk_nrestarts_end "$(dev systemctl show -p NRestarts --value kiosk.service)"
p boot_id_end "$(dev cat /proc/sys/kernel/random/boot_id)"

mkdir -p local/framepace || exit 2
stem="local/framepace/$stamp-$role-$engine"
if dev kiosk-drmgrab "$REMOTE_PPM" && dev cat "$REMOTE_PPM" > "$stem.ppm" && [ -s "$stem.ppm" ]; then
    p screenshot "sha256:$(sha256sum < "$stem.ppm" | cut -d' ' -f1)"
else
    p screenshot ""
fi
dev rm -f "$REMOTE_PPM"

{ printf '%s\n' "${P[@]}"; cat "$tmp/fp.rec"; } > "$stem.rec"
tools/kiosk-framepace.py "$stem.rec" > "$tmp/verdict"
rc=$?
cat "$tmp/verdict" >> "$stem.rec"
cat "$tmp/verdict"
echo "wrote $stem.rec"
exit "$rc"
