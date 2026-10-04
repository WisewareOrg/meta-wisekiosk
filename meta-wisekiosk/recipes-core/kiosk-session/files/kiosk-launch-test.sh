#!/usr/bin/env bash
# Self-test for kiosk-launch's env -> argv/env logic, without a reachable kiosk or cog --
# mirrors tools/kiosk-render-check-test.sh's "argument handling without a reachable kiosk".
#
#   meta-wisekiosk/recipes-core/kiosk-session/files/kiosk-launch-test.sh
#
# kiosk-launch's whole job is translating env vars (from /data/config/kiosk.conf via
# kiosk.service's EnvironmentFile) into cog's argv and its own exported env, then
# `exec cog ...`. There is nothing here to source as a pure function -- the logic IS the
# exec -- so this reaches the SHIPPED script by running it for real with a STUB `cog` on
# PATH that, instead of starting a browser, dumps its argv and the env vars kiosk-launch is
# supposed to set, and exits. kiosk-launch's own `#!/bin/sh` + exec means this stub really
# does replace the process image, so what the stub sees is exactly what a real cog would.
set -uo pipefail

HERE=$(dirname "$0")
TOOL="$HERE/kiosk-launch"
STUB=$(mktemp -d)
trap 'rm -rf "$STUB"' EXIT

cat > "$STUB/cog" << 'EOF'
#!/bin/sh
printf 'ARGV:'
for a in "$@"; do printf ' [%s]' "$a"; done
printf '\n'
printf 'ENV COG_PLATFORM_DRM_VIDEO_MODE=%s\n' "${COG_PLATFORM_DRM_VIDEO_MODE:-}"
printf 'ENV WEBKIT_INSPECTOR_HTTP_SERVER=%s\n' "${WEBKIT_INSPECTOR_HTTP_SERVER:-}"
EOF
chmod +x "$STUB/cog"

pass=0
fail=0

# run <extra-env-assignment>... -- prints the stub's captured ARGV/ENV lines to stdout.
run() {
    env -i PATH="$STUB:$PATH" KIOSK_URL=http://kiosk-launch-test.invalid/ "$@" sh "$TOOL"
}

# contains <haystack> <needle> -- bash substring test, not grep -q (set -o pipefail + grep -q
# inverts on a match via SIGPIPE), and not "${1/$2/}" (bash parameter-substitution patterns
# are GLOBS, so a needle containing "[" or "]" -- every ARGV line here -- matches wrong). A
# quoted needle inside [[ == *...* ]] is matched literally; only the bare *s are wildcards.
contains() { [[ "$1" == *"$2"* ]]; }

check() {
    local name=$1 out=$2 want_present=$3 want_absent=${4:-}
    local ok=1
    if [ -n "$want_present" ] && ! contains "$out" "$want_present"; then ok=0; fi
    if [ -n "$want_absent" ] && contains "$out" "$want_absent"; then ok=0; fi
    if [ "$ok" -eq 1 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name" >&2
        echo "      want present: '$want_present'  want absent: '$want_absent'" >&2
        echo "      got: $out" >&2
    fi
}

# --- default: no probe, no inspector --------------------------------------
OUT=$(run)
check "default: no --enable-developer-extras" "$OUT" "" "--enable-developer-extras"
check "default: no --enable-write-console-messages-to-stdout" "$OUT" "" \
    "--enable-write-console-messages-to-stdout"
check "default: no --user-script" "$OUT" "" "--user-script"
check "default: COG_PLATFORM_DRM_VIDEO_MODE defaults to 1280x720" "$OUT" \
    "ENV COG_PLATFORM_DRM_VIDEO_MODE=1280x720"
check "default: -P drm and the URL reach argv" "$OUT" \
    "ARGV: [-P] [drm] [http://kiosk-launch-test.invalid/]"

# --- KIOSK_PROBE=1, default script path ------------------------------------
OUT=$(run KIOSK_PROBE=1)
check "KIOSK_PROBE=1: console-to-stdout flag present" "$OUT" \
    "--enable-write-console-messages-to-stdout"
check "KIOSK_PROBE=1: default probe script path" "$OUT" \
    "--user-script=/home/root/kiosk-probe.js"
check "KIOSK_PROBE=1: inspector flag still absent" "$OUT" "" "--enable-developer-extras"

# --- KIOSK_PROBE=1 with a custom KIOSK_PROBE_SCRIPT ------------------------
OUT=$(run KIOSK_PROBE=1 KIOSK_PROBE_SCRIPT=/data/custom-probe.js)
check "KIOSK_PROBE_SCRIPT: custom path used verbatim" "$OUT" \
    "--user-script=/data/custom-probe.js"
check "KIOSK_PROBE_SCRIPT: the default path is NOT also present" "$OUT" "" \
    "/home/root/kiosk-probe.js"

# --- KIOSK_INSPECTOR=1 -------------------------------------------------------
OUT=$(run KIOSK_INSPECTOR=1)
check "KIOSK_INSPECTOR=1: --enable-developer-extras present" "$OUT" \
    "--enable-developer-extras"
check "KIOSK_INSPECTOR=1: WEBKIT_INSPECTOR_HTTP_SERVER bound to loopback:2999" "$OUT" \
    "ENV WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:2999"
check "KIOSK_INSPECTOR=1: probe flags still absent" "$OUT" "" \
    "--enable-write-console-messages-to-stdout"

# A custom bind address, honoured instead of the loopback default.
OUT=$(run KIOSK_INSPECTOR=1 KIOSK_INSPECTOR_BIND=0.0.0.0:3000)
check "KIOSK_INSPECTOR_BIND: custom bind address honoured" "$OUT" \
    "ENV WEBKIT_INSPECTOR_HTTP_SERVER=0.0.0.0:3000"

# --- COG_PLATFORM_DRM_VIDEO_MODE overridable from kiosk.conf ---------------
# kiosk.service's EnvironmentFile sets this BEFORE kiosk-launch runs, same as this test
# setting it in the environment it execs the tool with -- the ":=" default must not
# clobber an already-set value.
OUT=$(run COG_PLATFORM_DRM_VIDEO_MODE=1920x1080)
check "COG_PLATFORM_DRM_VIDEO_MODE: an already-set value is NOT overwritten" "$OUT" \
    "ENV COG_PLATFORM_DRM_VIDEO_MODE=1920x1080"

echo "kiosk-launch: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
