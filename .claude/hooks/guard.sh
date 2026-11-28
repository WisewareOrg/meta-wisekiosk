#!/usr/bin/env bash
# PreToolUse guard. Exit 2 blocks the tool call; stderr is fed back to the model.
#
# Device identity is read only from gitignored `local/device-identity.md`.
#
# Fail-open: no jq, no payload, no identity file or an unparseable input lets the call through. The
# exception is the prod grant: a missing, expired, malformed or symlinked grant counts as no grant.
#
# Self-test: bash tests/prechecks/guard-test.sh  (run by `just check` and CI)
set -uo pipefail

command -v jq > /dev/null 2>&1 || exit 0

payload=$(cat)
tool=$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null) || exit 0
[ -n "$tool" ] || exit 0

REPO=${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
# Like KIOSK_IDENTITY_FILE below, overridable so the self-test can use fixtures.
SYSFS=${KIOSK_SYSFS_ROOT:-/sys}

# `local/` exists only in the primary worktree, so the map resolves through
# `git rev-parse --git-common-dir`, which is relative to $REPO from the primary tree and absolute
# from a linked one.
IDFILE=${KIOSK_IDENTITY_FILE:-}
if [ -z "$IDFILE" ]; then
    IDFILE=$REPO/local/device-identity.md
    if [ ! -f "$IDFILE" ]; then
        gitcommon=$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null)
        if [ -n "$gitcommon" ]; then
            case "$gitcommon" in /*) ;; *) gitcommon=$REPO/$gitcommon ;; esac
            primary=$(cd "$gitcommon/.." 2>/dev/null && pwd)
            [ -n "$primary" ] && IDFILE=$primary/local/device-identity.md
        fi
    fi
fi
# A missing map is reported on stderr, for Bash calls only.
if [ ! -f "$IDFILE" ] && [ "$tool" = Bash ]; then
    printf '%s\n' "guard.sh: no local/device-identity.md reachable from $REPO -- the PROD-board rules (1, 3) are INERT for this call." >&2
fi

# Written by tools/prod-authorize.sh; resolved like IDFILE and overridable by KIOSK_PROD_AUTH_FILE.
PAFILE=${KIOSK_PROD_AUTH_FILE:-}
if [ -z "$PAFILE" ]; then
    PAFILE=$REPO/local/prod-auth
    if [ ! -f "$PAFILE" ]; then
        gitcommon=$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null)
        if [ -n "$gitcommon" ]; then
            case "$gitcommon" in /*) ;; *) gitcommon=$REPO/$gitcommon ;; esac
            primary=$(cd "$gitcommon/.." 2>/dev/null && pwd)
            [ -n "$primary" ] && PAFILE=$primary/local/prod-auth
        fi
    fi
fi

# A valid grant is `expires=<unix-int>` with that time strictly in the future and nothing else
# (trailing blank lines aside), and never a symlink; anything else is no grant.
grant_valid() {
    [ -f "$PAFILE" ] && [ ! -L "$PAFILE" ] || return 1
    content=$(cat "$PAFILE" 2>/dev/null)
    case "$content" in
        expires=*) exp=${content#expires=} ;;
        *) return 1 ;;
    esac
    case "$exp" in
        ''|*[!0-9]*) return 1 ;;
    esac
    [ "$exp" -gt "$(date +%s)" ]
}

# One `key = value` from the map's ```identity fence, empty when absent; the split is at the
# first `=`.
id_value() {
    [ -f "$IDFILE" ] || return 0
    awk -v want="$1" '
        /^```identity[[:space:]]*$/ { inblock = 1; next }
        inblock && /^```[[:space:]]*$/ { exit }
        inblock {
            eq = index($0, "=")
            if (eq == 0) next
            key = substr($0, 1, eq - 1)
            val = substr($0, eq + 1)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
            if (key == want) { print val; exit }
        }' "$IDFILE" 2>/dev/null
}

case "$tool" in
Bash)
    cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)
    [ -n "$cmd" ] || exit 0

    # A heredoc body is kept when its opener names a shell interpreter (ssh, bash, sh, zsh, dash, ksh)
    # and dropped otherwise; `.sh` filenames and `~/.ssh/` paths do not count as openers.
    code=$(printf '%s\n' "$cmd" | awk -v shre='(^|[^[:alnum:]_.-])(ssh|bash|sh|zsh|dash|ksh)([^[:alnum:]_.-]|$)' '
        !inhd && match($0, /<<-?['"'"'"]?[A-Za-z_][A-Za-z0-9_]*['"'"'"]?/) {
            t = substr($0, RSTART, RLENGTH)
            sub(/^<<-?['"'"'"]?/, "", t)
            sub(/['"'"'"]$/, "", t)
            term = t; inhd = 1; keep = ($0 ~ shre); print; next
        }
        inhd && $0 == term { inhd = 0; next }
        inhd { if (keep) print; next }
        { print }')

    # Whole-token view of the command, for matching an ssh target without building a regex from a
    # value. Shell punctuation and quotes are separators; `/` is not, so the MACHINE component of a
    # build path is not a bare token. The two tr sets are the same length: GNU tr pads a short second
    # set silently.
    norm=" $(printf '%s' "$code" | tr '@=:,"'"'"'();|&<>\t\n' '               ') "

    has_token() { [[ $norm == *" $1 "* ]]; }

    # Whitespace-split words of the command, with globbing off.
    set -f
    # shellcheck disable=SC2206
    WORDS=($code)
    set +f

    # Every ssh invocation as `target<TAB>remote-command` lines: the target is the first non-option
    # word after an ssh client, the remote command the word after it.
    ssh_pairs=$(
        armed=0
        skip=0
        target=""
        for w in ${WORDS+"${WORDS[@]}"}; do
            w=${w#[\"\']}
            w=${w%[\"\']}
            case "$w" in
                ssh | */ssh | *ssh.sh) armed=1; skip=0; target=""; continue ;;
            esac
            [ "$armed" -eq 1 ] || continue
            if [ "$skip" -eq 1 ]; then skip=0; continue; fi
            # Options before the target are the ssh client's; options after it belong to the remote
            # command's prefix and take a different list.
            if [ -z "$target" ]; then
                case "$w" in
                    # ssh options that take a separate value; the value is not a target.
                    -l | -p | -o | -i | -F | -b | -c | -m | -E | -J | -L | -R | -D | -W | -Q | -S | -e)
                        skip=1; continue ;;
                    -*) continue ;;
                esac
                target=$w; continue
            fi
            # A privilege or assignment prefix is not the remote command.
            case "$w" in
                sudo | doas | env | nice | ionice | command | time | timeout | stdbuf | setsid | nohup | chrt) continue ;;
                [A-Za-z_]*=*) continue ;;
                # Wrapper options that take a separate value, listed and not inferred: sudo's `-n` and `-i` take none.
                -u | -g | -U | -C | -p | -r | -t | --user | --group | --chdir)
                    skip=1; continue ;;
                -*) continue ;;
            esac
            printf '%s\t%s\n' "$target" "$w"
            target=""
            armed=0
        done
        [ -n "$target" ] && printf '%s\t\n' "$target"
    )
    # Bash string tests, not `| grep -q`: under pipefail the SIGPIPE status inverts a match.
    ssh_target() { [[ $'\n'$ssh_pairs$'\n' == *$'\n'"$1"$'\t'* ]]; }
    # Tolerates a path prefix on the verb (`/sbin/poweroff`).
    ssh_verb() {
        [[ $'\n'$ssh_pairs$'\n' == *$'\t'"$1"$'\n'* ]] && return 0
        [[ $'\n'$ssh_pairs$'\n' == *$'\t'*"/$1"$'\n'* ]]
    }

    # True when $1 is the value of a `host=` recipe argument (`just … host=<host>`); `MACHINE=<host>`
    # does not match.
    host_arg() { [[ $norm == *" host $1 "* ]]; }

    # Command position, tolerating privilege and assignment prefixes. Every rule that anchors a verb
    # uses it; the prefix is one repeating group of elements in any order.
    CMDWRAP='sudo|doas|env|nice|ionice|command|time|timeout|stdbuf|setsid|nohup|chrt'
    # An element: a wrapper word, a NAME=value assignment, an attached option, or
    # a bare numeric argument (`timeout 60`, `nice 10`).
    CMDELEM="((${CMDWRAP})|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*|-[^[:space:]]+|[0-9]+[smhd]?)[[:space:]]+"
    # An option's separate value (`-u root`) is accepted once, in the last slot before the command;
    # inside the repeating group it would swallow a real command as the value.
    CMDPOS="(^|[;&|(]|&&|\\|\\|)[[:space:]]*(${CMDELEM})*(-[^[:space:]]+[[:space:]]+[^-[:space:]][^[:space:]]*[[:space:]]+)?"

    # --- RULE 1 -- destructive operation aimed at the PROD board ---
    # A valid grant (grant_valid) widens only OTA/install/reboot/rollback/reprovision; flash,
    # tools/rauc-rotate and any power-off verb stay blocked (always_blocked). Read-only recipes are not
    # matched. Recipe and direct-script spellings are both matched. The target must be visible in the
    # same command: an exported `KIOSK_HOST` is invisible.
    prod_addr=$(id_value prod.address)
    prod_host=$(id_value public.prod.hostname)
    targets_prod=0
    [ -n "$prod_addr" ] && has_token "$prod_addr" && targets_prod=1
    # The hostname counts only in target position: `user@host`, the first non-option word after an
    # ssh client, or a `host=` recipe argument.
    if [ -n "$prod_host" ]; then
        case "$code" in *"@$prod_host"*) targets_prod=1 ;; esac
        ssh_target "$prod_host" && targets_prod=1
        host_arg "$prod_host" && targets_prod=1
    fi
    # Power verbs match at command position (CMDPOS) and as the remote command of an ssh (ssh_verb);
    # an argument of grep is neither. A verb ends at VERBEND: whitespace, one of `;&|)'"`, or end of
    # string.
    #
    # Residual: a quoted alternation whose power verb is any branch but the first
    # (`grep -cE 'panic|poweroff'`) reads as a chained command and blocks; `grep -e panic -e poweroff`
    # is allowed. `reboot` first is grant-scoped, not always-blocked.
    VERBEND="([[:space:];&|)'\"]|\$)"
    # `reboot` alone is grant-scoped, but `reboot -p/--poweroff/--halt`, `sh -c poweroff` (bash, zsh,
    # dash, ksh) and `init 0`/`telinit 0` are always blocked. Each is checked twice: CMDPOS covers local
    # and chained verbs, ssh_verb covers the remote command of an ssh call, which CMDPOS cannot reach,
    # gated on the captured verb being reboot, a shell or init.
    prod_reboot=0
    ssh_verb reboot && prod_reboot=1
    prod_power=0
    for v in shutdown halt poweroff kexec; do
        ssh_verb "$v" && prod_power=1
    done
    if printf '%s' "$code" | grep -qE \
        "${CMDPOS}(\\S*/)?reboot([[:space:]]+[^;&|]*)?[[:space:]](-p|--poweroff|--halt)${VERBEND}"; then
        prod_power=1
    fi
    if [ "$prod_reboot" -eq 1 ] && printf '%s' "$code" | grep -qE \
        "reboot([^;&|]*[[:space:]])?(-p|--poweroff|--halt)${VERBEND}"; then
        prod_power=1
    fi
    if printf '%s' "$code" | grep -qE \
        "${CMDPOS}(\\S*/)?(ba|z|da|k)?sh[[:space:]]+-c[[:space:]]+[\"']?(\\S*/)?(shutdown|halt|poweroff|kexec)${VERBEND}"; then
        prod_power=1
    fi
    prod_shc=0
    for v in sh bash zsh dash ksh; do
        ssh_verb "$v" && prod_shc=1
    done
    # -e: a pattern starting with `-` reads as a grep option.
    if [ "$prod_shc" -eq 1 ] && printf '%s' "$code" | grep -qE \
        -e "-c[[:space:]]+[\"']?(\\S*/)?(shutdown|halt|poweroff|kexec)${VERBEND}"; then
        prod_power=1
    fi
    if printf '%s' "$code" | grep -qE \
        "${CMDPOS}(\\S*/)?(tel)?init[[:space:]]+0${VERBEND}"; then
        prod_power=1
    fi
    prod_runlevel0=0
    for v in init telinit; do
        ssh_verb "$v" && prod_runlevel0=1
    done
    if [ "$prod_runlevel0" -eq 1 ] && printf '%s' "$code" | grep -qE \
        "(init|telinit)[[:space:]]+0${VERBEND}"; then
        prod_power=1
    fi

    # Verbs a valid grant (tools/prod-authorize.sh) allows against prod: an
    # OTA, install, rollback, reboot, rauc install or reprovision.
    grant_scoped=0
    if [ "$prod_reboot" -eq 1 ] || printf '%s' "$code" | grep -qE \
        "just[[:space:]]+(kiosk-ota|kiosk-install|kiosk-rollback|kiosk-reboot|provision-device)${VERBEND}|rauc[[:space:]]+install|systemctl([[:space:]]+-[^[:space:]]+)*[[:space:]]+reboot${VERBEND}|${CMDPOS}(\\S*/)?reboot${VERBEND}|tools/provision\\.sh[[:space:]]+device|kiosk-install\\.sh${VERBEND}"; then
        grant_scoped=1
    fi

    # Never allowed against prod, grant or not: flash, tools/rauc-rotate, and
    # any verb that leaves the board off rather than restarting it -- bare,
    # `/path/to/`-prefixed, or interleaved with systemctl options
    # (`systemctl --force poweroff`).
    always_blocked=0
    if [ "$prod_power" -eq 1 ] || printf '%s' "$code" | grep -qE \
        "just[[:space:]]+flash${VERBEND}|systemctl([[:space:]]+-[^[:space:]]+)*[[:space:]]+(poweroff|halt|kexec|shutdown)${VERBEND}|systemctl([[:space:]]+-[^[:space:]]+)*[[:space:]]+(start|isolate)[[:space:]]+(poweroff|halt)\\.target${VERBEND}|${CMDPOS}((\\S*/)?(shutdown|halt|poweroff|kexec))${VERBEND}|tools/rauc-rotate"; then
        always_blocked=1
    fi

    if [ "$targets_prod" -eq 1 ] && { [ "$always_blocked" -eq 1 ] || { [ "$grant_scoped" -eq 1 ] && ! grant_valid; }; }; then
        cat >&2 <<'MSG'
BLOCKED: that is a destructive operation aimed at the PROD board.

Prod is wall-mounted and is carrying the live soak run. An OTA, install,
rollback, reboot or reprovision there ends a run that cannot be replayed, and
a slot that comes up wrong costs a physical trip to the wall.

A valid grant (tools/prod-authorize.sh) allows the OTA/install/reboot/rollback/
reprovision half of that list. flash, rauc-rotate and any power-off verb
(shutdown, halt, poweroff, kexec) stay blocked regardless.

Retarget the BENCH board -- `local/device-identity.md` has the role map, and
`just find <cidr>` reports which address a swapped board took. Observation of
prod (kiosk-status, screenshot, kiosk-backup) is allowed
and is not what this blocked.
MSG
        exit 2
    fi

    # --- RULE 2 -- writing an image to a non-removable block device ---
    # Classification reads sysfs `removable`, not the device name; unknown device names are allowed.
    if printf '%s' "$code" | grep -qE \
        "${CMDPOS}(dd|bmaptool|wipefs|mkfs(\.[A-Za-z0-9]+)?|sgdisk|sfdisk|fdisk|parted|blkdiscard)([[:space:]]|$)|just[[:space:]]+(flash|provision-fresh-card)([[:space:]]|$)|of=[\"']?/dev/|>[[:space:]]*[\"']?/dev/(sd|hd|vd|xvd|nvme|mmcblk|loop|disk)|[[:space:]]tee([[:space:]]+-[^[:space:]]+)*[[:space:]]+[\"']?/dev/"; then
        # `/dev/disk/by-id/...` is captured whole and resolved under DEVROOT (KIOSK_DEV_ROOT) to its disk node.
        DEVROOT=${KIOSK_DEV_ROOT:-/dev}
        for dev in $(printf '%s' "$code" | grep -oE "/dev/(disk/by-[a-z]+/[^[:space:]\"'\`]+|[A-Za-z0-9]+)" | sort -u); do
            written=$dev
            node="$DEVROOT/${dev#/dev/}"
            if [ -e "$node" ]; then
                resolved=$(readlink -f "$node" 2>/dev/null)
                [ -n "$resolved" ] && dev="/dev/${resolved##*/}"
            fi
            base=${dev#/dev/}
            # Partition -> whole disk: sda1 -> sda, mmcblk0p1 -> mmcblk0,
            # nvme0n1p1 -> nvme0n1. sysfs carries `removable` on the disk only.
            case "$base" in
                mmcblk*p[0-9]*) base=${base%%p[0-9]*} ;;
                nvme*p[0-9]*)   base=${base%%p[0-9]*} ;;
                sd[a-z][0-9]*|vd[a-z][0-9]*|xvd[a-z][0-9]*|hd[a-z][0-9]*)
                    base=$(printf '%s' "$base" | sed 's/[0-9]*$//') ;;
            esac
            blocked=""
            case "$base" in
                nvme*|vd[a-z]|xvd[a-z])
                    blocked="$base is an internal system disk by name (NVMe / virtio); no card reader presents one" ;;
            esac
            if [ -z "$blocked" ] && [ -r "$SYSFS/block/$base/removable" ]; then
                if [ "$(cat "$SYSFS/block/$base/removable" 2>/dev/null)" = "0" ]; then
                    blocked="$SYSFS/block/$base/removable reports 0 -- this is a fixed disk, not a card"
                fi
            fi
            if [ -n "$blocked" ]; then
                cat >&2 <<MSG
BLOCKED: writing to $written ($dev), which is not removable media.

$blocked

Flashing the wrong device destroys the host, instantly and with no undo. Confirm
the card with \`lsblk -o NAME,SIZE,RM,MODEL\` (RM=1 is removable) and re-run
against that device. \`just flash\` expects the SD card, not a system disk.
MSG
                exit 2
            fi
        done
    fi

    # --- RULE 3 -- 2>/dev/null on an ssh to a board ---
    # Checked per command segment (split at `&&`, `||`, `;`), while the board is looked for across the
    # whole command: the array style puts the host on a definition line,
    #   ssh=(ssh -o ... root@<addr>); timeout 60 "${ssh[@]}" 'cmd' 2>/dev/null
    board_named=0
    for key in prod.address bench.address; do
        v=$(id_value "$key")
        [ -n "$v" ] && has_token "$v" && board_named=1
    done
    for key in public.prod.hostname bench.hostname; do
        v=$(id_value "$key")
        if [ -n "$v" ]; then
            case "$code" in *"@$v"*) board_named=1 ;; esac
            ssh_target "$v" && board_named=1
            host_arg "$v" && board_named=1
        fi
    done
    # `ssh` is word-anchored, so `ssh-keygen` and `.ssh/` paths do not match; kiosk-ssh.sh is named.
    # Counted with -c: `grep -q` under pipefail inverts a match.
    suppressed=$(printf '%s\n' "$code" | sed -e 's/&&/\n/g' -e 's/||/\n/g' -e 's/;/\n/g' \
                 | grep -cE "2>/dev/null.*((^|[^[:alnum:]_.-])ssh([^[:alnum:]_/-]|$)|kiosk-ssh\.sh)|((^|[^[:alnum:]_.-])ssh([^[:alnum:]_/-]|$)|kiosk-ssh\.sh).*2>/dev/null") || true
    if [ "$board_named" -eq 1 ] && [ "${suppressed:-0}" -gt 0 ]; then
        cat >&2 <<'MSG'
BLOCKED: 2>/dev/null on an ssh command to a kiosk board.

A suppressed probe cannot distinguish "the check is broken" from "the device is
broken". Let stderr through, or capture it and print it on failure.
MSG
        exit 2
    fi

    # --- RULE 4 -- the lifeline ---
    # Only the network path is protected; masking logind, userdbd, resolved and zram is allowed.
    if printf '%s' "$code" | grep -qE 'systemctl[^|;&]*(disable|mask|stop)' \
       && printf '%s' "$code" | grep -qE '(sshd|ssh\.service|ssh\.socket|wpa[-_]supplicant|systemd-networkd|dhcpcd|networking)'; then
        cat >&2 <<'MSG'
BLOCKED: that disables part of the LIFELINE (sshd / wpa_supplicant /
systemd-networkd / dhcpcd / networking).

SSH over wlan0 is the only way to reach this device, and there is no remote
undo. `/data/RECOVER.sh` reverses the boot trims that ARE reversible; this is
not one of them.
MSG
        exit 2
    fi

    # --- RULE 5 -- /boot has no A/B protection ---
    # Reads are allowed, as is `rauc status mark-*`. /boot/ counts only at the start of a path (after
    # whitespace, start of line or '='), so `arch/arm/boot/` and `/mnt/root/boot/` do not match.
    B='(^|[[:space:]]|=)/boot/'
    # The escape hatch is read from the command text, not the environment: the hook runs before the
    # command, so an inline `VAR=1 cmd` prefix is only text.
    if ! printf '%s' "$cmd" | grep -qE '(^|[[:space:]])KIOSK_ALLOW_BOOT_WRITE=1[[:space:]]' && {
         printf '%s' "$code" | grep -qE "${CMDPOS}fw_setenv([[:space:]]|$)" ||
         printf '%s' "$code" | grep -qE ">>?[[:space:]]*/boot/" ||
         printf '%s' "$code" | grep -qE "${CMDPOS}(rm|tee|truncate|dd|sed)([[:space:]][^|;&]*)?${B}" ||
         printf '%s' "$code" | grep -qE "${CMDPOS}(cp|mv)[[:space:]][^|;&]*${B}[^[:space:]|;&]*[[:space:]]*($|[;&|])"
       }; then
        cat >&2 <<'MSG'
BLOCKED: writing to /boot on a kiosk board.

/boot is the only partition with NO A/B protection -- the kernel and rootfs live
in the RAUC slots and fall back automatically, but cmdline.txt, config.txt and
uboot.env are SHARED, so a bad write breaks both slots at once and needs the
card pulled.

Kernel and boot changes ship by OTA instead, so that the A/B fallback covers
them. If a /boot write is genuinely required it needs explicit per-change owner
authorization (as ` panic=10` had, on a bench unit, 2026-08-12).

With that authorization, re-run with the escape hatch:
  KIOSK_ALLOW_BOOT_WRITE=1 <command>
MSG
        exit 2
    fi

    # --- RULE 6 -- `; echo $?` after a pipeline ---
    # A pipeline reports the last command's status.
    if printf '%s' "$code" | grep -qE '\|[^|]*;[[:space:]]*echo[^;]*\$\?'; then
        cat >&2 <<'MSG'
BLOCKED: `; echo $?` after a pipeline reports the LAST command's exit status
(usually tail/grep), not the work you care about. A failing gate reads green.

Instead: redirect to a file and test $? on the very next line, or read
"${PIPESTATUS[@]}" in bash / "$pipestatus[@]" in zsh -- indexed from 1 in zsh.
MSG
        exit 2
    fi

    # --- RULE 7 -- bare -f on pkill/pgrep ---
    # `-f` matches the harness's own command line. `-x -f '<exact argv>'` stays allowed: the first
    # option token must end in f.
    if printf '%s' "$code" | grep -qE "${CMDPOS}(pkill|pgrep)[[:space:]]+-[a-zA-Z]*f([[:space:]]|$)"; then
        cat >&2 <<'MSG'
BLOCKED: a bare -f on pkill/pgrep matches this harness's own shell command line,
because the pattern you are searching for is IN that command line. Killed the
tool call twice in this project (exit 144).

Instead:
  pid=$(pgrep -x -f "/bin/bash /full/path/to/script.sh" | head -1); kill "$pid"
  pkill -x <exact-process-name>
MSG
        exit 2
    fi
    ;;

Edit|Write|MultiEdit|NotebookEdit)
    fp=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
    [ -n "$fp" ] || exit 0
    case "$fp" in
    "$REPO"/*)
        # --- RULE 8 -- editing the build tree during a build ---
        # Fires only while a kas container is running.
        if timeout 5 docker ps --format '{{.Image}}' 2>/dev/null | grep -qi 'kas'; then
            cat >&2 <<MSG
BLOCKED: a kas/bitbake build container is running, and this edits the build tree.

bitbake parsed these recipes at start -- editing now either changes nothing or
invalidates a multi-hour run (docs/image.md §"What a rebuild costs").

Instead: develop in a git worktree and merge after the build finishes.
  git -C $REPO worktree list
MSG
            exit 2
        fi
        ;;
    esac
    ;;
esac
exit 0
