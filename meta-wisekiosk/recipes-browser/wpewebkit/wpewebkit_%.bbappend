# The recipe's release-with-debug-info off-arm puts -DCMAKE_BUILD_TYPE=Release after the
# reduce-size arm's MinSizeRel, and CMake takes the last one. A bbappend's :append lands after both.
EXTRA_OECMAKE:append = " -DCMAKE_BUILD_TYPE=MinSizeRel"

# Per recipe: a global INHERIT would add ccache-native and the exported CCACHE_* variables to every recipe's signature.
inherit ccache
