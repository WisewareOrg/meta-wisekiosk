# Appends firmware HDMI settings to config.txt: forced hotplug, CEA 1080p60 (group 1, mode 16).
# Firmware settings are inert under full KMS; this image builds firmware KMS (VC4DTBO =
# "vc4-fkms-v3d"), and panel-mode.cfg's video= sets the kiosk's mode on top.
do_deploy:append() {
    CONFIG=${DEPLOYDIR}/${BOOTFILES_DIR_NAME}/config.txt
    cat >> $CONFIG <<'RPICFG'

# --- kiosk display: carried from the Raspbian configuration ---
hdmi_force_hotplug=1
hdmi_group=1
hdmi_mode=16
RPICFG
}
