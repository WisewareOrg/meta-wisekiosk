SUMMARY = "WOFF2 web font container, reference encoder and decoder"
HOMEPAGE = "https://github.com/google/woff2"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=027c71da9e4664fdf192e6ec615f4d18"

SRC_URI = "git://github.com/google/woff2.git;branch=master;protocol=https"
# v1.0.2
SRCREV = "1bccf208bca986e53a647dfe4811322adb06ecf8"

S = "${WORKDIR}/git"

DEPENDS = "brotli"

inherit cmake pkgconfig

# Not required for the build to pass QA -- a bare relative RUNPATH matches
# neither the rpaths nor useless-rpaths ERROR_QA patterns -- but kept because
# the flag removes a junk relative RUNPATH that has no reason to ship.
EXTRA_OECMAKE = "-DCMAKE_SKIP_INSTALL_RPATH=ON"
