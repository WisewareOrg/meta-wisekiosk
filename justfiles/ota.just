# Reads: kiosk-host

kiosk-image-file := "build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/core-image-base-raspberrypi0-wifi.rootfs.ext4"
kiosk-bundle-file := "build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/update-bundle-raspberrypi0-wifi.raucb"

[group('ota')]
[doc("Build the RAUC update bundle, which `just build` does not")]
kiosk-bundle kconfig="kiosk-zero-w.yaml":
    tools/kas-run.sh shell {{kconfig}} -c "bitbake update-bundle"

[group('ota')]
[doc("Refuse a delivery that cannot work: slot size, stale bundle")]
kiosk-preflight image=kiosk-image-file bundle=kiosk-bundle-file host=kiosk-host:
    tools/kiosk-preflight.sh {{host}} {{image}} {{bundle}}

[group('ota')]
[doc("Stream a bundle to the board, install it and show slot state, without rebooting")]
kiosk-install host=kiosk-host bundle=kiosk-bundle-file:
    tools/kiosk-install.sh {{host}} {{bundle}}

[group('ota')]
[doc("Reboot the board and wait for the kiosk to answer again")]
kiosk-reboot host=kiosk-host timeout="300":
    tools/kiosk-reboot.sh {{host}} {{timeout}} && just kiosk-status {{host}}

[group('ota')]
[doc("Build the bundle, preflight, and install it on the device")]
kiosk-ota host=kiosk-host kconfig="kiosk-zero-w.yaml": (kiosk-bundle kconfig) (kiosk-preflight kiosk-image-file kiosk-bundle-file host) (kiosk-install host kiosk-bundle-file)
    @echo "Delivered and installed. Verify, then: just kiosk-reboot {{host}}"

[group('ota')]
[doc("Roll back to the other slot; both slots mount the same /data, so it is unchanged")]
kiosk-rollback host=kiosk-host:
    tools/kiosk-ssh.sh {{host}} 'rauc status mark-bad booted; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT'
    @echo "Marked booted slot bad. Now: just kiosk-reboot {{host}}"
