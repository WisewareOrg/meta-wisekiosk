# Compiles through ccache with poky's class (meta/classes/ccache.bbclass); the store's location is CCACHE_TOP_DIR in the ccache block of kiosk-zero-w.yaml.
inherit ccache
# The class sets no size limit; poky's ccache.conf is unbounded.
export CCACHE_MAXSIZE = "5G"
