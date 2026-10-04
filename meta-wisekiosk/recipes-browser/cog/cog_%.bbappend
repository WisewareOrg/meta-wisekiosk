FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

# --user-script=PATH: inject a script into the page at document start and
# print each title change to stdout as "TITLE <title>". kiosk-launch passes it
# when KIOSK_PROBE=1; without the option cog behaves as upstream.
#
# A platform named with -P that fails to come up makes cog exit non-zero
# instead of falling back to the default backend, so kiosk.service's
# Restart=always retries it and the journal shows why.
SRC_URI += " \
    file://0001-launcher-add-user-script-option.patch \
    file://0002-launcher-exit-when-a-requested-platform-fails.patch \
"
