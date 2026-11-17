#!/bin/bash
# Build the three bundles the image-update tests offer, inside the kas container.
#
# Each is a copy of the candidate's bundle with its rootfs edited, an install-check hook that
# refuses without this run's nonce, and the operator's signature.
#
# Usage: update_bundles.sh <run-dir> <nonce> <stamp> <probe-js>
#   run-dir   receives new-build.raucb, cannot-start.raucb, no-network.raucb and
#             candidate-info.json
#   nonce     the content /tmp/kiosk-update-nonce must hold on the board for the hook to accept
#   stamp     the value the new-build bundle's page carries in its kiosk-test-stamp meta tag
#   probe-js  the in-page probe, as a path inside the container
set -euo pipefail

usage="usage: update_bundles.sh <run-dir> <nonce> <stamp> <probe-js>"
run_dir=${1:?$usage}
nonce=${2:?$usage}
stamp=${3:?$usage}
probe_js=${4:?$usage}

cd "$run_dir"
work=$(mktemp -d "$run_dir/work.XXXXXX")
trap 'rm -rf "$work"' EXIT

bb_var() { sed -n "s/^$1=\"\(.*\)\"$/\1/p" "$2"; }

bitbake -e update-bundle > "$work/bundle-env.txt"
rauc_bin="$(bb_var STAGING_BINDIR_NATIVE "$work/bundle-env.txt")"
operator_key="$(bb_var RAUC_KEY_FILE "$work/bundle-env.txt")"
operator_cert="$(bb_var RAUC_CERT_FILE "$work/bundle-env.txt")"
keyring="$(bb_var RAUC_KEYRING_FILE "$work/bundle-env.txt")"
deploy_dir="$(bb_var DEPLOY_DIR_IMAGE "$work/bundle-env.txt")"
machine="$(bb_var MACHINE "$work/bundle-env.txt")"
: "${rauc_bin:?}" "${operator_key:?}" "${operator_cert:?}" "${keyring:?}" "${deploy_dir:?}" "${machine:?}"
candidate="$deploy_dir/update-bundle-$machine.raucb"

bitbake e2fsprogs-native -c addto_recipe_sysroot
bitbake -e e2fsprogs-native > "$work/e2fsprogs-env.txt"
e2fs_sbin="$(bb_var STAGING_SBINDIR_NATIVE "$work/e2fsprogs-env.txt")"
: "${e2fs_sbin:?}"
export PATH="$rauc_bin:$e2fs_sbin:$PATH"

rauc info --keyring="$keyring" --output-format=json "$candidate" > candidate-info.json
rauc extract --keyring="$keyring" "$candidate" "$work/extracted"

# The value of a manifest key within a section; empty when absent.
manifest_value() {
    awk -v section="[$1]" -v key="$2" '
        /^\[/ { in_section = ($0 == section); next }
        in_section && index($0, key "=") == 1 { print substr($0, length(key) + 2); exit }
    ' "$work/extracted/manifest.raucm"
}

compatible="$(manifest_value update compatible)"
version="$(manifest_value update version)"
build="$(manifest_value update build)"
rootfs_name="$(manifest_value image.rootfs filename)"
: "${compatible:?}" "${rootfs_name:?}"

# The names in a directory of an ext4 image, one per line.
dir_names() {
    debugfs -R "ls -p $2" "$1" 2> /dev/null | awk -F/ 'NF > 5 { print $6 }'
}

# Whether `$2` exists in the ext4 image `$1`.
exists() {
    local names
    names="$(dir_names "$1" "$(dirname "$2")")"
    grep -qxF "$(basename "$2")" <<< "$names"
}

# Run the debugfs commands on stdin against the image `$1`.
edit() {
    debugfs -w -f - "$1" > "$work/debugfs.log" 2>&1 || { cat "$work/debugfs.log" >&2; return 1; }
}

# Require that `$2` is gone from the image `$1`.
require_gone() {
    if exists "$1" "$2"; then
        echo "update_bundles.sh: $2 is still in the image" >&2
        exit 1
    fi
}

# Require that `$2` is in the image `$1`.
require_present() {
    if ! exists "$1" "$2"; then
        echo "update_bundles.sh: $2 is not in the image" >&2
        exit 1
    fi
}

stamp_the_page() {
    local image=$1 page=/srv/kiosk/index.html
    require_present "$image" "$page"
    debugfs -R "dump $page $work/index.html" "$image" 2> /dev/null
    sed -i 's|<head>|<head><meta name="kiosk-test-stamp" content="'"$stamp"'">|' "$work/index.html"
    grep -qF "content=\"$stamp\"" "$work/index.html" || {
        echo "update_bundles.sh: the page has no <head> to stamp" >&2
        exit 1
    }
    local fields uid gid mode
    fields="$(debugfs -R "stat $page" "$image" 2> /dev/null)"
    uid="$(sed -n 's/.*User: *\([0-9]*\).*/\1/p' <<< "$fields" | head -n 1)"
    gid="$(sed -n 's/.*Group: *\([0-9]*\).*/\1/p' <<< "$fields" | head -n 1)"
    mode="$(sed -n 's/.*Mode: *\([0-7]*\).*/\1/p' <<< "$fields" | head -n 1)"
    : "${uid:?}" "${gid:?}" "${mode:?}"
    edit "$image" <<EOF
rm $page
write $work/index.html $page
set_inode_field $page uid $uid
set_inode_field $page gid $gid
set_inode_field $page mode 0100$mode
EOF
}

install_the_probe() {
    local image=$1
    require_present "$image" /home/root
    require_gone "$image" /home/root/.surf
    edit "$image" <<EOF
mkdir /home/root/.surf
write $probe_js /home/root/.surf/script.js
set_inode_field /home/root/.surf uid 0
set_inode_field /home/root/.surf gid 0
set_inode_field /home/root/.surf mode 040755
set_inode_field /home/root/.surf/script.js uid 0
set_inode_field /home/root/.surf/script.js gid 0
set_inode_field /home/root/.surf/script.js mode 0100644
EOF
    require_present "$image" /home/root/.surf/script.js
}

remove_paths() {
    local image=$1 path
    shift
    for path in "$@"; do
        require_present "$image" "$path"
    done
    printf 'rm %s\n' "$@" | edit "$image"
    for path in "$@"; do
        require_gone "$image" "$path"
    done
}

remove_firmware() {
    local image=$1 name
    local -a paths=()
    while read -r name; do
        paths+=("/lib/firmware/brcm/$name")
    done < <(dir_names "$image" /lib/firmware/brcm | grep '^brcmfmac43430')
    if [ "${#paths[@]}" -eq 0 ]; then
        echo "update_bundles.sh: no brcmfmac43430 firmware in the image" >&2
        exit 1
    fi
    remove_paths "$image" "${paths[@]}"
}

# The hook runs in place of RAUC's own compatible check, so it keeps that refusal.
write_hook() {
    local hook=$1
    {
        cat <<EOF
#!/bin/sh
if [ "\$1" = install-check ]; then
    if [ "\$RAUC_MF_COMPATIBLE" != "\$RAUC_SYSTEM_COMPATIBLE" ]; then
        echo "test bundle: compatible mismatch" >&2
        exit 10
    fi
    if [ "\$(cat /tmp/kiosk-update-nonce 2> /dev/null)" != "$nonce" ]; then
        echo "test bundle: no run nonce" >&2
        exit 10
    fi
    exit 0
fi
EOF
        cat "$work/extracted/$(manifest_value hooks filename)"
    } > "$hook"
}

write_manifest() {
    local manifest=$1 kind=$2
    {
        echo "[update]"
        echo "compatible=$compatible"
        [ -z "$version" ] || echo "version=$version"
        [ -z "$build" ] || echo "build=$build"
        echo "description=test bundle: $kind"
        echo "[bundle]"
        echo "format=verity"
        echo "[hooks]"
        echo "filename=test-hook.sh"
        echo "hooks=install-check"
        echo "[image.rootfs]"
        echo "filename=$rootfs_name"
        echo "hooks=post-install"
    } > "$manifest"
}

build_bundle() {
    local kind=$1 dir="$work/$1"
    mkdir "$dir"
    cp --sparse=always "$work/extracted/$rootfs_name" "$dir/$rootfs_name"
    case "$kind" in
        new-build)
            stamp_the_page "$dir/$rootfs_name"
            install_the_probe "$dir/$rootfs_name"
            ;;
        cannot-start)
            remove_paths "$dir/$rootfs_name" /sbin/init /bin/sh
            ;;
        no-network)
            remove_firmware "$dir/$rootfs_name"
            ;;
    esac
    e2fsck -fn "$dir/$rootfs_name" > "$work/e2fsck.log" 2>&1 || {
        cat "$work/e2fsck.log" >&2
        echo "update_bundles.sh: the edited $kind image does not check clean" >&2
        exit 1
    }
    write_hook "$dir/test-hook.sh"
    write_manifest "$dir/manifest.raucm" "$kind"
    rauc bundle --cert="$operator_cert" --key="$operator_key" "$dir" "$run_dir/$kind.raucb"
    rm -rf "$dir"
}

for kind in new-build cannot-start no-network; do
    build_bundle "$kind"
done
