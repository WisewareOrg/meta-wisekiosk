# Per recipe: a global INHERIT would add ccache-native and the exported CCACHE_* variables to every recipe's signature.
inherit ccache
export CCACHE_MAXSIZE = "5G"
