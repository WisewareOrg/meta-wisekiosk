# Compiles through ccache with the class's settings set here until #412 Adopt poky's ccache class for wpewebkit's compile cache.
# CCACHE and every exported setting below are left out of signatures (bitbake.conf and the ccache block in kiosk-zero-w.yaml).
CCACHE = "ccache "
export CCACHE_DIR = "${CCACHE_TOP_DIR}/${MULTIMACH_TARGET_SYS}/${PN}"
export CCACHE_BASEDIR = "${TMPDIR}"
export CCACHE_NOHASHDIR = "1"
export CCACHE_CONFIGPATH = "${COREBASE}/meta/conf/ccache.conf"
export CCACHE_COMPILERCHECK = "%compiler% -dumpspecs"
export CCACHE_TEMPDIR = "${CCACHE_DIR}/tmp"
export CCACHE_MAXSIZE = "5G"
