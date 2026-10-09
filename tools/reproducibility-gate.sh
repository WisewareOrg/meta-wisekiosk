#!/usr/bin/env bash
# Refuse to put an image on a board unless the software on it can be rebuilt
# from what is published (#46).
#
#   tools/reproducibility-gate.sh --tree                                      -- clean + pushed
#   tools/reproducibility-gate.sh --image <rootfs.ext4> [--bundle <bundle.raucb>]
#                                                        -- ... and the image names HEAD,
#                                                           and (with --bundle) the bundle ties to it
#
# No override flag, by design -- see docs/layers-and-kas.md.
#
# Wiring is checked by tools/ci-guards.sh guard 10; this checks the tree and
# the artifact.

set -uo pipefail

usage() {
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
}

mode=""
image=""
bundle=""
bundle_given=0
# One mode, never two: last-wins would let `--image X --tree` run the weaker
# check while still reading as --image to tools/ci-guards.sh guard 10.
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
        --bundle) bundle_given=1; shift; bundle=${1-} ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

# The mode is REQUIRED and never inferred. A caller whose image variable came
# out empty must land here, not silently downgrade to the weaker tree-only
# check -- that failure would look identical to a passing gate.
case "$mode" in
    tree)
        if [ "$bundle_given" -eq 1 ]; then
            printf 'REFUSING: --bundle given with --tree -- --bundle needs --image\n' >&2
            exit 2
        fi
        ;;
    image)
        if [ -z "$image" ]; then
            printf 'REFUSING: --image was given an empty path\n' >&2
            exit 1
        fi
        if [ "$bundle_given" -eq 1 ] && [ -z "$bundle" ]; then
            printf 'REFUSING: --bundle was given an empty path\n' >&2
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
# --porcelain: untracked counts, and scope is the whole repo -- includes/ and
# patches/ are build inputs too.
dirty=$(git status --porcelain 2>/dev/null)
if [ -n "$dirty" ]; then
    refuse "the working tree is not clean -- this build is not reproducible from any commit:"
    printf '%s\n' "$dirty" | sed 's/^/        /' >&2
    printf '        commit or stash these, then rebuild.\n' >&2
else
    pass "working tree is clean"
fi

# --- (b) HEAD is published on origin --------------------------------------
# Reachability from ANY origin ref, not just origin/main: a PR branch is
# fetchable, which is all "someone else can check this out" requires.
#
# Never fetches: the answer must not depend on when this last ran.
remote=$(git ls-remote origin 2>/dev/null)
lsrc=$?
if [ $lsrc -ne 0 ] || [ -z "$remote" ]; then
    # Fail closed: offline is indistinguishable from never-pushed.
    refuse "cannot reach origin -- cannot prove $HEAD is published, so refusing"
    printf '        this gate never assumes; get online, or push, and retry.\n' >&2
else
    shas=$(printf '%s\n' "$remote" | awk '{print $1}' | sort -u)
    published=0
    while IFS= read -r sha; do
        [ -n "$sha" ] || continue
        if [ "$sha" = "$HEAD" ]; then published=1; break; fi
        # An ancestor test needs the remote commit in THIS object store.
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
# Only where a rootfs is in hand: the bundle-shipping recipes hold no rootfs
# to check /etc/buildinfo against, so they run --tree.
if [ "$mode" = "image" ]; then
    if [ ! -f "$image" ]; then
        refuse "no image artifact at $image -- nothing to attribute; build first"
    elif ! command -v debugfs > /dev/null 2>&1; then
        # Refuse, never skip: unreadable is not the same as absent.
        refuse "debugfs missing -- cannot read $image; install e2fsprogs"
    else
        info=$(debugfs -R "cat /etc/buildinfo" "$image" 2>/dev/null | tr -d '\r')
        # image-buildinfo writes "%-17s = %s:%s%s" per BBLAYERS entry, so the
        # layer's own line is `meta-wisekiosk = <branch>:<sha>[ -- modified]`.
        # ` -- modified` ignored; check (a) is authoritative.
        rev=$(awk '$1 == "meta-wisekiosk" && $2 == "=" { print $3; exit }' <<< "$info")
        commit=${rev##*:}
        if [ -z "$info" ]; then
            refuse "no /etc/buildinfo in $image -- this image cannot name the commit it was built from"
            printf '        is INHERIT += "image-buildinfo" still in kiosk-zero-w.yaml?\n' >&2
        elif [ -z "$rev" ]; then
            refuse "/etc/buildinfo in $image has no meta-wisekiosk layer line -- the layer was renamed or is not in BBLAYERS"
        elif ! [[ "$commit" =~ ^[0-9a-f]{40}$ ]]; then
            # image-buildinfo writes the literal <unknown> and does not fail.
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

# --- (d) the bundle ties to the image --------------------------------------
if [ "$mode" = "image" ] && [ "$bundle_given" -eq 1 ]; then
    if [ ! -f "$bundle" ]; then
        refuse "no bundle at $bundle -- nothing to tie to $image"
    elif ! command -v unsquashfs > /dev/null 2>&1; then
        refuse "unsquashfs missing -- cannot read $bundle; install squashfs-tools"
    elif ! command -v sha256sum > /dev/null 2>&1; then
        refuse "sha256sum missing -- cannot hash $image"
    else
        # A bundle is squashfs with an appended signature; unsquashfs reads
        # from the front and needs no key to cat one named file.
        manifest=$(unsquashfs -cat "$bundle" manifest.raucm 2>/dev/null)
        bundle_digest=$(awk '
            /^\[image\.rootfs\]/ { in_section = 1; next }
            /^\[/ { in_section = 0 }
            in_section && /^sha256=/ { sub(/^sha256=/, ""); print; exit }
        ' <<< "$manifest")
        image_digest=$(sha256sum "$image" | awk '{print $1}')
        if [ -z "$bundle_digest" ]; then
            refuse "no [image.rootfs] sha256= in $bundle's own manifest.raucm -- cannot tie it to $image"
        elif [ "$bundle_digest" != "$image_digest" ]; then
            refuse "the bundle does not tie to this image:"
            printf '        bundle rootfs digest: %s\n' "$bundle_digest" >&2
            printf '        image sha256:         %s\n' "$image_digest" >&2
        else
            pass "bundle ties to the image (sha256=$image_digest)"
        fi
    fi
fi

if [ "$refused" -ne 0 ]; then
    printf '\nreproducibility gate REFUSED\n' >&2
    exit 1
fi
printf '\nreproducibility gate passed\n'
