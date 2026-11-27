SUMMARY = "Node.js (upstream binary, build host only)"
DESCRIPTION = "The official Node.js binary tarball, unpacked into the native sysroot for the frontend build; it never reaches the device."
HOMEPAGE = "https://nodejs.org/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=91714ce137cce8ffea829e50d3341205"

# Does not provide nodejs-native (meta-oe does); consumers name this recipe in DEPENDS.

# Maps BUILD_ARCH to upstream's tarball arch name; an unlisted host keeps its own name and has
# no checksum below.
def node_build_arch(d):
    arch = d.getVar("BUILD_ARCH")
    return {"x86_64": "x64", "aarch64": "arm64"}.get(arch, arch)

NODE_BUILD_ARCH = "${@node_build_arch(d)}"

# Checksums at https://nodejs.org/dist/v${PV}/SHASUMS256.txt
SRC_URI = "https://nodejs.org/dist/v${PV}/node-v${PV}-linux-${NODE_BUILD_ARCH}.tar.xz;name=linux_${NODE_BUILD_ARCH}"
SRC_URI[linux_x64.sha256sum] = "ca70e9e349de048b9522abb3adc05b3bd6f43c5ffd3ec57916c7da292f59f022"
SRC_URI[linux_arm64.sha256sum] = "7a6353f63eb3d04765004b4adf172616243e4522434635cb1d26288658b04ab5"

# Upstream version check is limited to major 26.
UPSTREAM_CHECK_URI = "https://nodejs.org/dist/"
UPSTREAM_CHECK_REGEX = "v(?P<pver>26(\.\d+)+)/"

CVE_PRODUCT = "nodejs:node.js"

S = "${WORKDIR}/node-v${PV}-linux-${NODE_BUILD_ARCH}"

inherit native

do_compile() {
    :
}

# The tarball is a prefix layout; bin/npm and bin/npx are relative symlinks into lib/node_modules.
do_install() {
    install -d ${D}${prefix}
    cp --preserve=mode,timestamps -R ${S}/bin ${S}/include ${S}/lib ${S}/share ${D}${prefix}/
}
