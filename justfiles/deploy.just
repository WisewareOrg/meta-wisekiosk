# Reads: machine, image-name, rootfs-file, fleet-key, keys-root

wic-file := "build/tmp-" + machine + "/deploy/images/" + machine + "/" + image-name + "-" + machine + ".rootfs.wic.bz2"

[group('deploy')]
[doc("Flash the WIC image to an SD card, once it is shown to bake the fleet keyring")]
flash device:
    tools/flash.sh "{{device}}" "{{wic-file}}" "{{rootfs-file}}" "{{keys-root}}/{{fleet-key}}/signing.cert.pem"

[group('provision')]
[doc("Mount a fresh card's /data (partition 4), provision it from secrets.yaml, unmount")]
provision-fresh-card device mountpoint="/mnt/kiosk-data":
    tools/provision-fresh-card.sh {{device}} {{mountpoint}}
