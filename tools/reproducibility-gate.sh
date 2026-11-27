#!/usr/bin/env bash
# Refuse to put an image on a board unless the software on it can be rebuilt
# from what is published.
#
#   tools/reproducibility-gate.sh --tree                 -- clean + pushed
#   tools/reproducibility-gate.sh --image <rootfs.ext4>  -- ... and the image names HEAD
#
# There is no override flag; see docs/image.md.

set -uo pipefail

usage() {
    sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'
}

mode=""
image=""
# Exactly one mode flag is accepted.
set_mode() {
    [ -z "$mode" ] || {
        printf 'two mode flags given: --%s and %s\n\n' "$mode" "$1" >&2
        usage >&2
        exit 2
    }
    mode=${1#--}
}
while [ $# -gt 0 ]; do
    case "$1" in
        --tree)  set_mode "$1" ;;
        --image) set_mode "$1"; shift; image=${1-} ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

# The mode is required and never inferred; an empty --image path is refused.
case "$mode" in
    tree) ;;
    image)
        if [ -z "$image" ]; then
            printf 'REFUSING: --image was given an empty path\n' >&2
            exit 1
        fi
        ;;
    *) printf 'no mode given\n\n' >&2; usage >&2; exit 2 ;;
esac

root=$(git rev-parse --show-toplevel 2>/dev/null) \
    || { printf 'REFUSING: not inside a git repository -- nothing to attribute an image to\n' >&2; exit 1; }
cd "$root" || exit 2

HEAD=$(git rev-parse HEAD 2>/dev/null)
if [ -z "$HEAD" ]; then
    printf 'REFUSING: this repository has no HEAD commit\n' >&2
    exit 1
fi

refused=0
refuse() { printf 'REFUSING: %s\n' "$*" >&2; refused=1; }
pass()   { printf 'ok    %s\n' "$*"; }

# --- (a) the working tree is clean ----------------------------------------
# --porcelain counts untracked files; the scope is the whole repo.
dirty=$(git status --porcelain 2>/dev/null)
if [ -n "$dirty" ]; then
    refuse "the working tree is not clean -- this build is not reproducible from any commit:"
    printf '%s\n' "$dirty" | sed 's/^/        /' >&2
    printf '        commit or stash these, then rebuild.\n' >&2
else
    pass "working tree is clean"
fi

# --- (b) HEAD is published on origin --------------------------------------
# HEAD counts as published when reachable from any origin ref. Never fetches.
remote=$(git ls-remote origin 2>/dev/null)
lsrc=$?
if [ $lsrc -ne 0 ] || [ -z "$remote" ]; then
    refuse "cannot reach origin -- cannot prove $HEAD is published, so refusing"
    printf '        this gate never assumes; get online, or push, and retry.\n' >&2
else
    shas=$(printf '%s\n' "$remote" | awk '{print $1}' | sort -u)
    published=0
    while IFS= read -r sha; do
        [ -n "$sha" ] || continue
        if [ "$sha" = "$HEAD" ]; then published=1; break; fi
        # The ancestor test needs the remote commit in the local object store.
        git cat-file -e "${sha}^{commit}" 2>/dev/null || continue
        if git merge-base --is-ancestor "$HEAD" "$sha" 2>/dev/null; then published=1; break; fi
    done <<< "$shas"
    if [ "$published" -eq 1 ]; then
        pass "HEAD ($HEAD) is published on origin"
    else
        refuse "HEAD is on no ref published to origin:"
        printf '        %s\n' "$HEAD" >&2
        printf '        push the branch, then rebuild -- an unpushed commit cannot be checked out by anyone else.\n' >&2
    fi
fi

# --- (c) the image names HEAD ---------------------------------------------
# Runs only with --image, where a rootfs is in hand.
if [ "$mode" = "image" ]; then
    if [ ! -f "$image" ]; then
        refuse "no image artifact at $image -- nothing to attribute; build first"
    elif ! command -v debugfs > /dev/null 2>&1; then
        refuse "debugfs missing -- cannot read $image; install e2fsprogs"
    else
        info=$(debugfs -R "cat /etc/buildinfo" "$image" 2>/dev/null | tr -d '\r')
        # The layer's line is `meta-wisekiosk = <branch>:<sha>[ -- modified]`; ` -- modified` is ignored.
        rev=$(awk '$1 == "meta-wisekiosk" && $2 == "=" { print $3; exit }' <<< "$info")
        commit=${rev##*:}
        if [ -z "$info" ]; then
            refuse "no /etc/buildinfo in $image -- this image cannot name the commit it was built from"
            printf '        is INHERIT += "image-buildinfo" still in kiosk-zero-w.yaml?\n' >&2
        elif [ -z "$rev" ]; then
            refuse "/etc/buildinfo in $image has no meta-wisekiosk layer line -- the layer was renamed or is not in BBLAYERS"
        elif ! [[ "$commit" =~ ^[0-9a-f]{40}$ ]]; then
            refuse "the image records '$commit', not a 40-character sha -- the build could not read its own git tree, so nothing in $image is attributable"
        elif [ "$commit" != "$HEAD" ]; then
            refuse "the image was not built from HEAD:"
            printf '        image: %s\n' "$commit" >&2
            printf '        HEAD : %s\n' "$HEAD" >&2
            printf "        run \`just build\` -- the host sha is in do_image's\n" >&2
            printf '        signature (kiosk-buildinfo-cachesafe), so a moved HEAD re-stamps.\n' >&2
            printf '        Or check out the commit the image came from.\n' >&2
        else
            pass "image names HEAD ($commit)"
        fi
    fi
fi

if [ "$refused" -ne 0 ]; then
    printf '\nreproducibility gate REFUSED\n' >&2
    exit 1
fi
printf '\nreproducibility gate passed\n'
