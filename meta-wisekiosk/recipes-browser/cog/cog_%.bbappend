FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

# --user-script=PATH: inject a script into the page at document start and
# print each title change to stdout as "TITLE <title>". kiosk-launch passes it
# when KIOSK_PROBE=1; without the option cog behaves as upstream.
SRC_URI += "file://0001-launcher-add-user-script-option.patch"
