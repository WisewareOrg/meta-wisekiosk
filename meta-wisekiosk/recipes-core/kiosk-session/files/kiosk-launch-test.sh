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
#
# The stub MODELS cog 0.18.5 + GLib 2.78.6's GOptionEntry parsing of the boolean
# --enable-* flags, rather than just dumping raw argv -- every one of them is
# OPTIONAL_ARG: "--enable-X=VAL" sets VAL, but a BARE "--enable-X" consumes the very NEXT
# argv token as its value whenever that token does not itself start with '-' (it is
# consumed, not left positional). kiosk-launch passes these bare (no "="), so
# KIOSK_INSPECTOR=1 alone gives cog argv "... --enable-developer-extras <KIOSK_URL>", and
# the URL -- not starting with '-' -- is SWALLOWED as the flag's value: cog never receives
# a positional URL at all. A stub that only checks "is the flag's name present in argv"
# (this file's previous version) cannot see that bug, because the flag's name IS present
# either way -- it is the CONSEQUENCE, not the flag's presence, that differs.
set -uo pipefail

HERE=$(dirname "$0")
TOOL="$HERE/kiosk-launch"
STUB=$(mktemp -d)
trap 'rm -rf "$STUB"' EXIT

cat > "$STUB/cog" << 'EOF'
#!/bin/sh
# Models GLib's OPTIONAL_ARG parsing for the two boolean --enable-* flags and the
# MANDATORY-arg -P/--user-script, faithfully enough to reproduce the real bug above.
# Boolean-from-string (GLib): true for no value, "true" (case-insensitive) or "1";
# everything else, including a swallowed positional, is false.
dev_extras_seen=0; dev_extras_val=
console_seen=0; console_val=
user_script=
features_val=
features_count=0
unrecognized=
unrecog_count=0
mode=
positional=
npos=0
argi=0
features_argi=
positional_argi=

while [ $# -gt 0 ]; do
    argi=$((argi + 1))
    case "$1" in
        -P)
            mode=$2; shift 2 ;;
        --enable-developer-extras=*)
            dev_extras_seen=1; dev_extras_val=${1#*=}; shift ;;
        --enable-developer-extras)
            dev_extras_seen=1; shift
            if [ $# -gt 0 ]; then
                case "$1" in
                    -*) dev_extras_val= ;;
                    *)  dev_extras_val=$1; shift ;;
                esac
            fi
            ;;
        --enable-write-console-messages-to-stdout=*)
            console_seen=1; console_val=${1#*=}; shift ;;
        --enable-write-console-messages-to-stdout)
            console_seen=1; shift
            if [ $# -gt 0 ]; then
                case "$1" in
                    -*) console_val= ;;
                    *)  console_val=$1; shift ;;
                esac
            fi
            ;;
        --user-script=*)
            user_script=${1#*=}; shift ;;
        --features=*)
            features_val=${1#*=}; features_count=$((features_count + 1))
            [ -z "$features_argi" ] && features_argi=$argi
            shift ;;
        -*)
            # Any flag this stub does not otherwise recognise -- including the SECOND
            # half of a --features value that got word-split instead of staying one
            # argument -- is counted, not silently dropped, so that failure mode shows
            # up as a non-zero UNRECOGNIZED_COUNT rather than disappearing.
            unrecognized="$unrecognized$1 "; unrecog_count=$((unrecog_count + 1)); shift ;;
        *)
            positional="$positional$1 "; npos=$((npos + 1))
            [ -z "$positional_argi" ] && positional_argi=$argi
            shift ;;
    esac
done

norm_bool() {
    case "$1" in
        ""|[Tt][Rr][Uu][Ee]|1) echo true ;;
        *) echo false ;;
    esac
}

if [ "$dev_extras_seen" = 1 ]; then dev_extras=$(norm_bool "$dev_extras_val"); else dev_extras=false; fi
if [ "$console_seen" = 1 ]; then console=$(norm_bool "$console_val"); else console=false; fi

printf 'POSITIONAL:%s\n' "$positional"
printf 'NPOS:%s\n' "$npos"
printf 'DEV_EXTRAS:%s\n' "$dev_extras"
printf 'CONSOLE_STDOUT:%s\n' "$console"
printf 'USER_SCRIPT:%s\n' "$user_script"
printf 'FEATURES_VAL:%s\n' "$features_val"
printf 'FEATURES_COUNT:%s\n' "$features_count"
printf 'FEATURES_ARGI:%s\n' "$features_argi"
printf 'POSITIONAL_ARGI:%s\n' "$positional_argi"
printf 'UNRECOGNIZED_COUNT:%s\n' "$unrecog_count"
printf 'MODE:%s\n' "$mode"
printf 'ENV_COG_PLATFORM_DRM_VIDEO_MODE:%s\n' "${COG_PLATFORM_DRM_VIDEO_MODE:-}"
printf 'ENV_WEBKIT_INSPECTOR_HTTP_SERVER:%s\n' "${WEBKIT_INSPECTOR_HTTP_SERVER:-}"
EOF
chmod +x "$STUB/cog"

pass=0
fail=0
KIOSK_URL_TEST='http://kiosk-launch-test.invalid/'

# run <extra-env-assignment>... -- prints the stub's captured, PARSED fields.
run() {
    env -i PATH="$STUB:$PATH" KIOSK_URL="${KIOSK_URL_TEST}" "$@" sh "$TOOL"
}

# contains <haystack> <needle> -- bash substring test, not grep -q (set -o pipefail + grep -q
# inverts on a match via SIGPIPE), and not "${1/$2/}" (bash parameter-substitution patterns
# are GLOBS, so a needle containing "[" or "]" would match wrong). A quoted needle inside
# [[ == *...* ]] is matched literally; only the bare *s are wildcards.
contains() { [[ "$1" == *"$2"* ]]; }

# field <output> <LABEL> -- the value after "LABEL:", trimmed of nothing (POSITIONAL can
# legitimately hold trailing whitespace from the stub's own "$1 " accumulator).
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

# check_combo <name> <KIOSK_INSPECTOR 0|1> <KIOSK_PROBE 0|1> [KIOSK_COG_FEATURES value] --
# the properties the fix must hold in EVERY combination, read from the stub's PARSED
# fields, not from raw argv text: (1) cog's positional argument is EXACTLY $KIOSK_URL and
# there is exactly one of it, (2) developer-extras is true iff KIOSK_INSPECTOR=1, (3)
# write-console-messages-to-stdout is true iff KIOSK_PROBE=1, (4) cog receives EXACTLY
# ONE "--features=<value>" argument, BEFORE the positional URL in argv: the default
# -UseDamagingInformationForCompositing alone when
# KIOSK_COG_FEATURES is unset, the default then a comma then the value, whole and never
# word-split, when it is set. (5) zero unrecognised flags reach cog -- the check that
# catches a word-split value's second half landing as a stray, silently-ignored token
# instead of showing up as a visible mismatch.
check_combo() {
    local name=$1 inspector=$2 probe=$3 features=${4:-} \
          out pos npos dev console feat_val feat_count feat_argi pos_argi unrecog_count \
          want_dev want_console want_feat ok=1
    local -a env_args=()
    [ "$inspector" = 1 ] && env_args+=("KIOSK_INSPECTOR=1")
    [ "$probe" = 1 ] && env_args+=("KIOSK_PROBE=1")
    [ -n "$features" ] && env_args+=("KIOSK_COG_FEATURES=$features")
    out=$(run "${env_args[@]}")

    pos=$(field "$out" POSITIONAL)
    npos=$(field "$out" NPOS)
    dev=$(field "$out" DEV_EXTRAS)
    console=$(field "$out" CONSOLE_STDOUT)
    feat_val=$(field "$out" FEATURES_VAL)
    feat_count=$(field "$out" FEATURES_COUNT)
    feat_argi=$(field "$out" FEATURES_ARGI)
    pos_argi=$(field "$out" POSITIONAL_ARGI)
    unrecog_count=$(field "$out" UNRECOGNIZED_COUNT)
    want_dev=false; [ "$inspector" = 1 ] && want_dev=true
    want_console=false; [ "$probe" = 1 ] && want_console=true

    [ "$npos" = 1 ] || ok=0
    contains "$pos" "$KIOSK_URL_TEST" || ok=0
    [ "$dev" = "$want_dev" ] || ok=0
    [ "$console" = "$want_console" ] || ok=0
    [ "$unrecog_count" = 0 ] || ok=0
    want_feat=$FEATURES_DEFAULT${features:+,$features}
    [ "$feat_count" = 1 ] || ok=0
    [ "$feat_val" = "$want_feat" ] || ok=0
    # --features before the URL: the flag's argv position must precede the
    # positional's. Both are set whenever feat_count=1 and npos=1 hold already.
    [ -n "$feat_argi" ] && [ -n "$pos_argi" ] && [ "$feat_argi" -lt "$pos_argi" ] || ok=0

    if [ "$ok" -eq 1 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  $name" >&2
        echo "      npos=$npos (want 1)  positional='$pos' (want to contain the URL)" >&2
        echo "      dev_extras=$dev (want $want_dev)  console_stdout=$console (want $want_console)" >&2
        echo "      features_count=$feat_count (want 1)  features_val='$feat_val' (want '$want_feat')" >&2
        echo "      features_argi=$feat_argi  positional_argi=$pos_argi (want features before positional)" >&2
        echo "      unrecognized_count=$unrecog_count (want 0)" >&2
        echo "      full output: $out" >&2
    fi
}

FEATURES_DEFAULT='-UseDamagingInformationForCompositing'
check_combo "neither KIOSK_INSPECTOR nor KIOSK_PROBE" 0 0
check_combo "KIOSK_INSPECTOR=1 alone -- the bug: a bare flag would swallow the URL" 1 0
check_combo "KIOSK_PROBE=1 alone" 0 1
check_combo "KIOSK_INSPECTOR=1 and KIOSK_PROBE=1 together" 1 1

# cog's real syntax (kiosk-launch's own comment, 3ee4a1e) is a COMMA list with NO spaces --
# cog trims only TRAILING whitespace per item, so a comma-SPACE value ("-A, -B") itself
# makes cog exit on the leading space in " -B". This is the realistic value, used for the
# round-trip and ordering checks below.
FEATURES_TEST='-AcceleratedCompositing,-ThreadedScrolling'
check_combo "KIOSK_COG_FEATURES unset -- the default alone" 0 0 ''
check_combo "KIOSK_COG_FEATURES set (comma-separated, the real syntax) -- one argument" \
    0 0 "$FEATURES_TEST"
check_combo "KIOSK_COG_FEATURES set alongside KIOSK_INSPECTOR and KIOSK_PROBE" \
    1 1 "$FEATURES_TEST"

# A SEPARATE, deliberately-not-realistic probe: kiosk-launch's own exec line must not
# re-split the value on whitespace regardless of whether cog itself would accept it -- that
# is a shell-quoting property of kiosk-launch, not a claim about what cog considers valid.
# A naive, unquoted `--features=$KIOSK_COG_FEATURES` would split this into two argv tokens.
check_features_value_with_a_space_is_not_word_split() {
    local out feat_count feat_val unrecog_count value='plugh xyzzy'
    out=$(run "KIOSK_COG_FEATURES=$value")
    feat_count=$(field "$out" FEATURES_COUNT)
    feat_val=$(field "$out" FEATURES_VAL)
    unrecog_count=$(field "$out" UNRECOGNIZED_COUNT)
    if [ "$feat_count" = 1 ] && [ "$feat_val" = "$FEATURES_DEFAULT,$value" ] && [ "$unrecog_count" = 0 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  KIOSK_COG_FEATURES with an embedded space must reach cog as one argument" >&2
        echo "      features_count=$feat_count (want 1)  features_val='$feat_val' (want '$FEATURES_DEFAULT,$value')" >&2
        echo "      unrecognized_count=$unrecog_count (want 0)" >&2
        echo "      full output: $out" >&2
    fi
}
check_features_value_with_a_space_is_not_word_split

# Set-but-empty (KIOSK_COG_FEATURES=, an empty value, not an absent variable) must pass
# the default alone too -- a `[ -n "$KIOSK_COG_FEATURES" ]`-style guard treats both the same,
# but a `${KIOSK_COG_FEATURES+...}` (no colon) guard would not, and only this fixture can
# tell the two apart: check_combo's "unset" case never sets the variable at all.
check_features_set_but_empty_passes_the_default_alone() {
    local out feat_count feat_val unrecog_count
    out=$(run "KIOSK_COG_FEATURES=")
    feat_count=$(field "$out" FEATURES_COUNT)
    feat_val=$(field "$out" FEATURES_VAL)
    unrecog_count=$(field "$out" UNRECOGNIZED_COUNT)
    if [ "$feat_count" = 1 ] && [ "$feat_val" = "$FEATURES_DEFAULT" ] && [ "$unrecog_count" = 0 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "FAIL  KIOSK_COG_FEATURES= (set but empty) should pass the default alone" >&2
        echo "      features_count=$feat_count (want 1)  features_val='$feat_val' (want '$FEATURES_DEFAULT')  unrecognized_count=$unrecog_count (want 0)" >&2
        echo "      full output: $out" >&2
    fi
}
check_features_set_but_empty_passes_the_default_alone

# --- default: mode and env unaffected by the argv-parsing fix --------------
OUT=$(run)
check "default: COG_PLATFORM_DRM_VIDEO_MODE defaults to 1280x720" "$OUT" \
    "ENV_COG_PLATFORM_DRM_VIDEO_MODE:1280x720"

# --- KIOSK_PROBE=1, default and custom script path -------------------------
OUT=$(run KIOSK_PROBE=1)
check "KIOSK_PROBE=1: default probe script path" "$OUT" \
    "USER_SCRIPT:/home/root/kiosk-probe.js"

OUT=$(run KIOSK_PROBE=1 KIOSK_PROBE_SCRIPT=/data/custom-probe.js)
check "KIOSK_PROBE_SCRIPT: custom path used verbatim" "$OUT" \
    "USER_SCRIPT:/data/custom-probe.js"
check "KIOSK_PROBE_SCRIPT: the default path is NOT also present" "$OUT" "" \
    "/home/root/kiosk-probe.js"

# --- KIOSK_INSPECTOR=1: bind address ----------------------------------------
OUT=$(run KIOSK_INSPECTOR=1)
check "KIOSK_INSPECTOR=1: WEBKIT_INSPECTOR_HTTP_SERVER bound to loopback:2999" "$OUT" \
    "ENV_WEBKIT_INSPECTOR_HTTP_SERVER:127.0.0.1:2999"

# A custom bind address, honoured instead of the loopback default.
OUT=$(run KIOSK_INSPECTOR=1 KIOSK_INSPECTOR_BIND=0.0.0.0:3000)
check "KIOSK_INSPECTOR_BIND: custom bind address honoured" "$OUT" \
    "ENV_WEBKIT_INSPECTOR_HTTP_SERVER:0.0.0.0:3000"

# --- COG_PLATFORM_DRM_VIDEO_MODE overridable from kiosk.conf ---------------
# kiosk.service's EnvironmentFile sets this BEFORE kiosk-launch runs, same as this test
# setting it in the environment it execs the tool with -- the ":=" default must not
# clobber an already-set value.
OUT=$(run COG_PLATFORM_DRM_VIDEO_MODE=1920x1080)
check "COG_PLATFORM_DRM_VIDEO_MODE: an already-set value is NOT overwritten" "$OUT" \
    "ENV_COG_PLATFORM_DRM_VIDEO_MODE:1920x1080"

echo "kiosk-launch: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
