#!/usr/bin/env bash
# Self-test for kiosk-launch's env -> argv/env logic, without a reachable kiosk or
# wpe-kiosk -- mirrors tools/kiosk-render-check-test.sh's "argument handling without a
# reachable kiosk".
#
#   meta-wisekiosk/recipes-core/kiosk-session/files/kiosk-launch-test.sh
#
# kiosk-launch's whole job is translating env vars (from /data/config/kiosk.conf via
# kiosk.service's EnvironmentFile) into wpe-kiosk's argv and exported env, then
# `exec wpe-kiosk "$KIOSK_URL"`. There is nothing here to source as a pure function --
# the logic IS the exec -- so this reaches the SHIPPED script by running it for real
# with a STUB `wpe-kiosk` on PATH that, instead of starting a browser, dumps its argv
# and the env it was given, and exits. kiosk-launch's own `#!/bin/sh` + exec means this
# stub really does replace the process image, so what the stub sees is exactly what a
# real wpe-kiosk would.
#
# wpe-kiosk takes no flags at all: every one of cog's former --enable-*/--features
# arguments is now a plain `export`ed environment variable, and argv is always exactly
# [$KIOSK_URL]. The old GLib GOptionEntry OPTIONAL_ARG bug model (a bare --enable-X flag
# swallowing the next argv token, including the URL) is retired along with the flags it
# was modelling -- there is no argv position left to swallow.
set -uo pipefail

HERE=$(dirname "$0")
TOOL="$HERE/kiosk-launch"
STUB=$(mktemp -d)
trap 'rm -rf "$STUB"' EXIT

cat > "$STUB/wpe-kiosk" << 'EOF'
#!/bin/sh
printf 'ARGC:%s\n' "$#"
i=0
for a in "$@"; do i=$((i + 1)); printf 'ARGV%s:%s\n' "$i" "$a"; done
# _SET uses ${VAR+1} (not ${VAR:-}) so "set but empty" is distinct from "unset" --
# ${VAR+1} expands to "1" whenever VAR is set, even to an empty string.
printf 'WPE_KIOSK_MODE:%s\n' "${WPE_KIOSK_MODE:-}"
printf 'WPE_KIOSK_FEATURES:%s\n' "${WPE_KIOSK_FEATURES:-}"
printf 'WPE_KIOSK_SCRIPT_SET:%s\n' "${WPE_KIOSK_SCRIPT+1}"
printf 'WPE_KIOSK_SCRIPT:%s\n' "${WPE_KIOSK_SCRIPT:-}"
printf 'WPE_KIOSK_CONSOLE_SET:%s\n' "${WPE_KIOSK_CONSOLE+1}"
printf 'WPE_KIOSK_CONSOLE:%s\n' "${WPE_KIOSK_CONSOLE:-}"
printf 'WPE_KIOSK_INSPECTOR_SET:%s\n' "${WPE_KIOSK_INSPECTOR+1}"
printf 'WPE_KIOSK_INSPECTOR:%s\n' "${WPE_KIOSK_INSPECTOR:-}"
printf 'WEBKIT_INSPECTOR_HTTP_SERVER_SET:%s\n' "${WEBKIT_INSPECTOR_HTTP_SERVER+1}"
printf 'WEBKIT_INSPECTOR_HTTP_SERVER:%s\n' "${WEBKIT_INSPECTOR_HTTP_SERVER:-}"
EOF
chmod +x "$STUB/wpe-kiosk"

pass=0
fail=0
KIOSK_URL_TEST='http://kiosk-launch-test.invalid/'
FEATURES_DEFAULT='-UseDamagingInformationForCompositing'

# run <extra-env-assignment>... -- prints the stub's captured fields.
run() {
    env -i PATH="$STUB:$PATH" KIOSK_URL="${KIOSK_URL_TEST}" "$@" sh "$TOOL"
}

# contains <haystack> <needle> -- bash substring test, not grep -q (set -o pipefail +
# grep -q inverts on a match via SIGPIPE), and not "${1/$2/}" (bash parameter-
# substitution patterns are GLOBS, so a needle containing "[" or "]" would match
# wrong). A quoted needle inside [[ == *...* ]] is matched literally; only the bare
# *s are wildcards.
contains() { [[ "$1" == *"$2"* ]]; }

# field <output> <LABEL> -- the value after "LABEL:".
field() { printf '%s\n' "$1" | sed -n "s/^$2://p"; }

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

# check_combo <name> <KIOSK_INSPECTOR 0|1> <KIOSK_PROBE 0|1> [KIOSK_COG_FEATURES value]
# -- the properties the launcher must hold in EVERY combination: (1) argv is exactly
# [$KIOSK_URL], nothing else; (2) WPE_KIOSK_INSPECTOR is set iff KIOSK_INSPECTOR=1,
# never present otherwise; (3) WPE_KIOSK_CONSOLE and WPE_KIOSK_SCRIPT are set iff
# KIOSK_PROBE=1, never present otherwise; (4) WPE_KIOSK_FEATURES is the default alone
# when KIOSK_COG_FEATURES is unset, the default then a comma then the value, whole
# and never word-split, when it is set.
check_combo() {
    local name=$1 inspector=$2 probe=$3 features=${4:-} \
          out argc argv1 insp_set console_set script_set feat_val \
          want_feat ok=1
    local -a env_args=()
    [ "$inspector" = 1 ] && env_args+=("KIOSK_INSPECTOR=1")
    [ "$probe" = 1 ] && env_args+=("KIOSK_PROBE=1")
    [ -n "$features" ] && env_args+=("KIOSK_COG_FEATURES=$features")
    out=$(run "${env_args[@]}")

    argc=$(field "$out" ARGC)
    argv1=$(field "$out" ARGV1)
    insp_set=$(field "$out" WPE_KIOSK_INSPECTOR_SET)
    console_set=$(field "$out" WPE_KIOSK_CONSOLE_SET)
    script_set=$(field "$out" WPE_KIOSK_SCRIPT_SET)
    feat_val=$(field "$out" WPE_KIOSK_FEATURES)
    want_feat=$FEATURES_DEFAULT${features:+,$features}

    [ "$argc" = 1 ] || ok=0
    [ "$argv1" = "$KIOSK_URL_TEST" ] || ok=0
    if [ "$inspector" = 1 ]; then [ "$insp_set" = 1 ] || ok=0
    else [ -z "$insp_set" ] || ok=0; fi
    if [ "$probe" = 1 ]; then [ "$console_set" = 1 ] && [ "$script_set" = 1 ] || ok=0
    else [ -z "$console_set" ] && [ -z "$script_set" ] || ok=0; fi
    [ "$feat_val" = "$want_feat" ] || ok=0

    if [ "$ok" -eq 1 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name" >&2
        echo "      argc=$argc (want 1)  argv1='$argv1' (want '$KIOSK_URL_TEST')" >&2
        echo "      inspector_set=$insp_set (want $( [ "$inspector" = 1 ] && echo 1 || echo unset))" >&2
        echo "      console_set=$console_set script_set=$script_set (want $( [ "$probe" = 1 ] && echo 'both 1' || echo 'both unset'))" >&2
        echo "      features='$feat_val' (want '$want_feat')" >&2
        echo "      full output: $out" >&2
    fi
}

check_combo "neither KIOSK_INSPECTOR nor KIOSK_PROBE" 0 0
check_combo "KIOSK_INSPECTOR=1 alone" 1 0
check_combo "KIOSK_PROBE=1 alone" 0 1
check_combo "KIOSK_INSPECTOR=1 and KIOSK_PROBE=1 together" 1 1

# wpe-kiosk's real syntax (kiosk-launch's own comment) is a COMMA list with NO spaces --
# the same composition rule as cog's, carried over unchanged. This is the realistic
# value, used for the round-trip checks below.
FEATURES_TEST='-AcceleratedCompositing,-ThreadedScrolling'
check_combo "KIOSK_COG_FEATURES unset -- the default alone" 0 0 ''
check_combo "KIOSK_COG_FEATURES set (comma-separated, the real syntax) -- one value" \
    0 0 "$FEATURES_TEST"
check_combo "KIOSK_COG_FEATURES set alongside KIOSK_INSPECTOR and KIOSK_PROBE" \
    1 1 "$FEATURES_TEST"

# A value containing a space reaches WPE_KIOSK_FEATURES whole: kiosk-launch builds it
# with a quoted shell assignment, never an unquoted argv interpolation, so there is no
# word-splitting mechanism left to break this -- a regression guard carried over from
# the exec-line-splitting bug this property used to probe for.
check_features_value_with_a_space_is_not_word_split() {
    local out feat_val value='plugh xyzzy'
    out=$(run "KIOSK_COG_FEATURES=$value")
    feat_val=$(field "$out" WPE_KIOSK_FEATURES)
    if [ "$feat_val" = "$FEATURES_DEFAULT,$value" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  KIOSK_COG_FEATURES with an embedded space must reach WPE_KIOSK_FEATURES whole" >&2
        echo "      got '$feat_val' want '$FEATURES_DEFAULT,$value'" >&2
    fi
}
check_features_value_with_a_space_is_not_word_split

# Set-but-empty (KIOSK_COG_FEATURES=, an empty value, not an absent variable) must pass
# the default alone too -- a `[ -n "$KIOSK_COG_FEATURES" ]`-style guard treats both the
# same, but a `${KIOSK_COG_FEATURES+...}` (no colon) guard would not, and only this
# fixture can tell the two apart: check_combo's "unset" case never sets the variable
# at all.
check_features_set_but_empty_passes_the_default_alone() {
    local out feat_val
    out=$(run "KIOSK_COG_FEATURES=")
    feat_val=$(field "$out" WPE_KIOSK_FEATURES)
    if [ "$feat_val" = "$FEATURES_DEFAULT" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  KIOSK_COG_FEATURES= (set but empty) should pass the default alone" >&2
        echo "      got '$feat_val' want '$FEATURES_DEFAULT'" >&2
    fi
}
check_features_set_but_empty_passes_the_default_alone

# --- default: mode unaffected by anything else ------------------------------
OUT=$(run)
check "default: WPE_KIOSK_MODE defaults to 1280x720" "$OUT" \
    "WPE_KIOSK_MODE:1280x720"

# --- KIOSK_PROBE=1, default and custom script path -------------------------
OUT=$(run KIOSK_PROBE=1)
check "KIOSK_PROBE=1: default probe script path" "$OUT" \
    "WPE_KIOSK_SCRIPT:/home/root/kiosk-probe.js"

OUT=$(run KIOSK_PROBE=1 KIOSK_PROBE_SCRIPT=/data/custom-probe.js)
check "KIOSK_PROBE_SCRIPT: custom path used verbatim" "$OUT" \
    "WPE_KIOSK_SCRIPT:/data/custom-probe.js"
check "KIOSK_PROBE_SCRIPT: the default path is NOT also present" "$OUT" "" \
    "/home/root/kiosk-probe.js"

# A path containing a space reaches WPE_KIOSK_SCRIPT whole, for the same reason as
# WPE_KIOSK_FEATURES above -- a quoted `export`, never an argv interpolation.
check_probe_script_with_a_space_is_not_word_split() {
    local out script_val argc value='/data/a b.js'
    out=$(run KIOSK_PROBE=1 "KIOSK_PROBE_SCRIPT=$value")
    script_val=$(field "$out" WPE_KIOSK_SCRIPT)
    argc=$(field "$out" ARGC)
    if [ "$script_val" = "$value" ] && [ "$argc" = 1 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  KIOSK_PROBE_SCRIPT with an embedded space must reach WPE_KIOSK_SCRIPT whole" >&2
        echo "      script='$script_val' (want '$value')  argc=$argc (want 1)" >&2
    fi
}
check_probe_script_with_a_space_is_not_word_split

# --- KIOSK_INSPECTOR=1: bind address ----------------------------------------
OUT=$(run KIOSK_INSPECTOR=1)
check "KIOSK_INSPECTOR=1: WEBKIT_INSPECTOR_HTTP_SERVER bound to loopback:2999" "$OUT" \
    "WEBKIT_INSPECTOR_HTTP_SERVER:127.0.0.1:2999"

# A custom bind address, honoured instead of the loopback default.
OUT=$(run KIOSK_INSPECTOR=1 KIOSK_INSPECTOR_BIND=0.0.0.0:3000)
check "KIOSK_INSPECTOR_BIND: custom bind address honoured" "$OUT" \
    "WEBKIT_INSPECTOR_HTTP_SERVER:0.0.0.0:3000"

# --- KIOSK_INSPECTOR unset: neither inspector var is present ----------------
OUT=$(run)
check "default: WPE_KIOSK_INSPECTOR is not set" "$OUT" "WPE_KIOSK_INSPECTOR_SET:" ""
check "default: WEBKIT_INSPECTOR_HTTP_SERVER is not set" "$OUT" \
    "WEBKIT_INSPECTOR_HTTP_SERVER_SET:" ""

# --- COG_PLATFORM_DRM_VIDEO_MODE overridable from kiosk.conf ---------------
# kiosk.service's EnvironmentFile sets this BEFORE kiosk-launch runs, same as this test
# setting it in the environment it execs the tool with -- the ":=" default must not
# clobber an already-set value.
OUT=$(run COG_PLATFORM_DRM_VIDEO_MODE=1920x1080)
check "COG_PLATFORM_DRM_VIDEO_MODE: an already-set value becomes WPE_KIOSK_MODE verbatim" \
    "$OUT" "WPE_KIOSK_MODE:1920x1080"

# --- the exec line itself, textually: kiosk-soak.sh's own CMD= extraction depends on
# this exact shape (a bare `exec <name>`, no path, no quoting around the name) to learn
# the launcher binary's name -- a two-sides-drift check, the same reason sentinel_pair
# checks exist in the other tools' self-tests.
SOAK="$HERE/../../kiosk-soak/files/kiosk-soak.sh"
if [ -f "$SOAK" ]; then
    extracted=$(grep -oE '^[[:space:]]*exec[[:space:]]+[A-Za-z0-9._-]+' "$TOOL" \
        | head -n1 | awk '{print $2}')
    if [ "$extracted" = "wpe-kiosk" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  kiosk-soak.sh's CMD= extraction would read launcher name '$extracted', want 'wpe-kiosk'" >&2
    fi
else
    fail=$((fail + 1))
    echo "FAIL  $SOAK not found -- cannot check the exec-line extraction kiosk-soak.sh depends on" >&2
fi

echo "kiosk-launch: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
