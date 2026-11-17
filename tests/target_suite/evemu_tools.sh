#!/bin/bash
# Build evemu-tools and its library for the board, inside the kas container.
#
# Usage: evemu_tools.sh <run-dir>
#   run-dir  receives helpers/ (evemu-device, evemu-play, libevemu.so.3, libevdev.so.2),
#            version (evemu-tools' PKGV) and packages (the runtime package names)
set -euo pipefail

run_dir=${1:?usage: evemu_tools.sh <run-dir>}

bitbake evemu-tools libevdev

cd "$run_dir"
bitbake -e evemu-tools > bitbake-env.txt
deploy_ipk="$(sed -n 's/^DEPLOY_DIR_IPK="\(.*\)"$/\1/p' bitbake-env.txt)"
: "${deploy_ipk:?}"

# `debian.bbclass` may rename a single-library package, so the runtime names are looked up.
evemu_pkg="$(oe-pkgdata-util lookup-pkg evemu-tools)"
evdev_pkg="$(oe-pkgdata-util lookup-pkg libevdev)"
: "${evemu_pkg:?}" "${evdev_pkg:?}"
printf '%s\n%s\n' "$evemu_pkg" "$evdev_pkg" > packages
oe-pkgdata-util read-value PKGV "$evemu_pkg" > version

# The deploy directory outlasts a version bump, so the ipk is matched on the version too.
ipk_of() {
    local pkg=$1 pkgv matches
    pkgv="$(oe-pkgdata-util read-value PKGV "$pkg")"
    matches=("$deploy_ipk"/*/"${pkg}_${pkgv}"-*.ipk)
    if [ "${#matches[@]}" -ne 1 ] || [ ! -e "${matches[0]}" ]; then
        echo "evemu_tools.sh: expected one ipk for $pkg $pkgv, found: ${matches[*]}" >&2
        return 1
    fi
    echo "${matches[0]}"
}

mkdir root helpers
for pkg in "$evemu_pkg" "$evdev_pkg"; do
    ar p "$(ipk_of "$pkg")" data.tar.zst | tar --zstd -x -C root
done

cp -L root/usr/bin/evemu-device root/usr/bin/evemu-play \
    root/usr/lib/libevemu.so.3 root/usr/lib/libevdev.so.2 helpers/
