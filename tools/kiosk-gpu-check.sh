#!/usr/bin/env bash
# Checks that a cog/WPE process holds /dev/dri open with vc4 or v3d mapped.
#
#   tools/kiosk-gpu-check.sh root@<host>    read-only
#
# Exit: 0 GPU path present; 1 not present; 2 could not tell.
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
    echo "mapped. This cannot distinguish Hardware from Shared Memory rendering."
    return 0
}

main() {
if [ "${1:-}" = "" ]; then
    echo "usage: kiosk-gpu-check.sh <ssh-target>" >&2
    exit 2
fi
HOST=$1
MODE=${2:-}

HERE=$(dirname "$0")

if [ -n "$MODE" ]; then
    echo "unknown argument '$MODE'" >&2
    exit 2
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
