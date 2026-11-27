# Rebuilds libicudata with ICU_DATA_FILTER_FILE=${WORKDIR}/filter.json, which keeps locale "en"
# and every feature category. do_make_icudata is a no-op unless make-icudata is in PACKAGECONFIG,
# so both lines below are needed. WebKit build-depends on ICU, so this rebuilds WebKit.

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI:append:class-target = " file://filter.json"
PACKAGECONFIG:append:class-target = " make-icudata"
