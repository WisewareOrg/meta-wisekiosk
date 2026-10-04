#!/usr/bin/env bash
# Checks that a cog/WPE process holds /dev/dri open with vc4 or v3d mapped.
#
#   tools/kiosk-gpu-check.sh root@<host>                       read-only
#   tools/kiosk-gpu-check.sh root@<host> --capture [out.png]   mutating: kiosk on webkit://gpu, screenshot, restore
#
# Exit: 0 GPU path present (--capture: captured); 1 not present (--capture: failed); 2 could not tell.
# Reasoning and measurements: docs/issue_investigation/gpu_compositing/README.md §"Configuration under test"
set -uo pipefail

# The browser family by process name. The device matches /proc comm, which holds
# at most 15 characters, so each name is compared truncated to 15.
KIOSK_BROWSER_PROCS='WPEWebProcess|WPENetworkProcess|WPEGPUProcess|cog'

gpu_verdict() {
    local probe=$1 procs gpu hw

    procs=$(printf '%s\n' "$probe" | grep -c '^proc ')
    if [ "$procs" -eq 0 ]; then
        echo "no cog or WPE process on the device -- nothing to measure, not a pass" >&2
        return 2
    fi

    if [ "$(printf '%s\n' "$probe" | grep -c '^cap grep_o=0')" -ne 0 ]; then
        echo "cannot tell: the device's grep has no -o, so no drv= field is readable." >&2
        return 2
    fi
    if [ "$(printf '%s\n' "$probe" | grep -c '^proc .* drifd=?')" -ne 0 ]; then
        echo "cannot tell: a process's fd directory could not be read (drifd=? above)." >&2
        return 2
    fi

    gpu=$(printf '%s\n' "$probe" | grep -cE '^proc .* drifd=[1-9]')
    if [ "$gpu" -eq 0 ]; then
        echo "NO GPU path: no web process holds /dev/dri open. WebKit is compositing in" >&2
        echo "software, or not compositing at all. See" >&2
        echo "docs/issue_investigation/gpu_compositing/README.md." >&2
        return 1
    fi

    hw=$(printf '%s\n' "$probe" | grep -cE '^proc .* drifd=[1-9].*(vc4|v3d)_dri\.so')
    if [ "$hw" -eq 0 ]; then
        if [ "$(printf '%s\n' "$probe" | grep -cE '^proc .* drifd=[1-9] drv=\?')" -ne 0 ]; then
            echo "cannot tell: the process holding /dev/dri has unreadable maps (drv=?)," >&2
            echo "so which driver it mapped is unknown. Not a software verdict." >&2
            return 2
        fi
        echo "SOFTWARE mesa: a web process holds /dev/dri open, but no vc4/v3d driver" >&2
        echo "is mapped -- the drv= field above says which." >&2
        return 1
    fi

    echo "GPU path present: a web process holds /dev/dri open with a vc4/v3d driver"
    echo "mapped. Confirm the mode itself by reading webkit://gpu's Renderer row --"
    echo "this cannot distinguish Hardware from Shared Memory."
    return 0
}

main() {
if [ "${1:-}" = "" ]; then
    echo "usage: kiosk-gpu-check.sh <ssh-target> [--capture [out.png]]" >&2
    exit 2
fi
HOST=$1
MODE=${2:-}
OUT=${3:-}

HERE=$(dirname "$0")

if [ -n "$MODE" ] && [ "$MODE" != "--capture" ]; then
    echo "unknown argument '$MODE' -- expected --capture" >&2
    exit 2
fi

if [ "$MODE" = "--capture" ]; then
    restore() {
        local out rc
        out=$("$HERE/kiosk-ssh.sh" "$HOST" 'sh -s' <<'RESTORE'
[ -f /data/config/kiosk.conf.gpucheck-bak ] || { echo "nothing-to-restore"; exit 0; }
mv /data/config/kiosk.conf.gpucheck-bak /data/config/kiosk.conf
systemctl restart kiosk
echo "restored"
RESTORE
        )
        rc=$?
        if [ "$rc" -eq 0 ]; then
            case "$out" in
                *restored*)          echo "kiosk.conf restored from its backup; kiosk restarted" ;;
                *nothing-to-restore*) echo "no backup on the device -- kiosk.conf was never swapped" ;;
                *)                   echo "restore reported neither outcome: $out" >&2 ;;
            esac
        else
            echo "RESTORE FAILED (rc=$rc): /data/config/kiosk.conf.gpucheck-bak is" >&2
            echo "still on $HOST. Move it back over kiosk.conf by hand -- until then" >&2
            echo "the panel is showing webkit://gpu, not the kiosk page." >&2
        fi
    }
    trap restore EXIT INT TERM

    "$HERE/kiosk-ssh.sh" "$HOST" 'sh -s' <<'PREP' || {
grep -q '^KIOSK_URL=' /data/config/kiosk.conf || exit 3
cp /data/config/kiosk.conf /data/config/kiosk.conf.gpucheck-bak
sed -i '/^KIOSK_URL=/d' /data/config/kiosk.conf
echo 'KIOSK_URL=webkit://gpu' >> /data/config/kiosk.conf
systemctl restart kiosk
PREP
        echo "could not stage the probe URL on $HOST (exit 3 means kiosk.conf has" >&2
        echo "no KIOSK_URL line at all, so there is nothing to put back)." >&2
        restore; trap - EXIT; exit 2; }

    up=0
    pollrc=0
    for _ in $(seq 1 30); do
        up=$("$HERE/kiosk-ssh.sh" "$HOST" 'pgrep -x cog | wc -l')
        pollrc=$?
        [ $pollrc -eq 0 ] && [ "${up:-0}" != "0" ] && break
        sleep 2
    done
    if [ $pollrc -ne 0 ]; then
        echo "cannot tell: lost contact with $HOST while waiting for cog (ssh exited" >&2
        echo "$pollrc). Whether the browser came back is unknown. kiosk.conf is put" >&2
        echo "back on the way out -- verify it by hand if that restore also failed." >&2
        restore; trap - EXIT; exit 2
    fi
    if [ "${up:-0}" = "0" ]; then
        echo "cog did not come back up within 60s -- not capturing. kiosk.conf is" >&2
        echo "put back on the way out." >&2
        restore; trap - EXIT; exit 1
    fi
    sleep 5

    "$HERE/kiosk-screenshot.sh" "$HOST" ${OUT:+"$OUT"} || { echo "capture failed" >&2; restore; trap - EXIT; exit 1; }

    echo
    echo "Read the 'Hardware Acceleration Information' table in the capture:"
    echo "  Renderer: DMABuf (Supported buffers: Hardware, Shared Memory)  -- GPU"
    echo "  Renderer row ABSENT                                           -- no mode at all"
    echo "This mode reports only that the capture came back, not what it shows."
    restore; trap - EXIT; exit 0
fi

# Heredoc runs under busybox sh on the device.
# shellcheck disable=SC2029  # KIOSK_BROWSER_PROCS expands here, on the client
PROBE=$("$HERE/kiosk-ssh.sh" "$HOST" "PROCS='$KIOSK_BROWSER_PROCS' sh -s" <<'REMOTE'
PAT=$(printf '%s\n' "$PROCS" | tr '|' '\n' | cut -c1-15 | tr '\n' '|' | sed 's/|$//')
if echo x_dri.so | grep -oE '[a-z0-9_]+_dri\.so' > /dev/null 2>&1; then
    echo "cap grep_o=1"
else
    echo "cap grep_o=0"
fi
for d in /proc/[0-9]*; do
    c=$(cat "$d/comm" 2>/dev/null) || continue
    printf '%s\n' "$c" | grep -qxE "$PAT" || continue
    pid=${d#/proc/}
    if fds=$(ls -l "$d/fd" 2>/dev/null); then
        dri=$(printf '%s\n' "$fds" | grep -c '/dev/dri/')
    else
        dri="?"
    fi
    if [ -r "$d/maps" ]; then
        drv=$(grep -oE '[a-z0-9_]+_dri\.so' "$d/maps" 2>/dev/null | sort -u | tr '\n' ' ')
        drv=${drv:-none}
    else
        drv="?"
    fi
    echo "proc $c pid=$pid drifd=$dri drv=$drv"
done
grep -E '^Cma(Total|Free):' /proc/meminfo 2>/dev/null | sed 's/^/mem /'
[ -e /sys/class/drm/card0 ] && echo "drm card0 present" || echo "drm card0 absent"
REMOTE
)
rc=$?
[ $rc -eq 0 ] || { echo "cannot read $HOST: ssh exited $rc" >&2; exit 2; }

printf '%s\n' "$PROBE" | sed 's/^/  /'

gpu_verdict "$PROBE"
exit $?
}

if [ "${KIOSK_GPU_CHECK_LIB:-0}" != "1" ]; then
    main "$@"
fi
