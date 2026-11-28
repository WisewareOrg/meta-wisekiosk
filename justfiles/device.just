# Reads: kiosk-host, py

[group('device')]
[doc("Show whether the kiosk service is active, the booted slot and the boot-order counters")]
kiosk-status host=kiosk-host:
    tools/kiosk-ssh.sh {{host}} 'systemctl is-active kiosk; rauc status; fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT'

[group('device')]
[doc("Sweep a /24 and report Raspberry Pi OUIs from the best neighbour table available")]
find cidr:
    tools/kiosk-find.sh {{cidr}}

[group('device')]
[doc("Infer browser state from TCP connections to the served page; run on the host serving it, kiosk-addr is the kiosk's address")]
tcp-state kiosk-addr port="8080":
    tools/kiosk-tcp-state.sh {{kiosk-addr}} {{port}}

[group('device')]
[doc("Read the panel's buffer into a PNG, and fail if it is blank")]
screenshot host=kiosk-host out="":
    {{py}} meta-wisekiosk/recipes-core/kiosk-drmgrab/kiosk-screenshot.py {{host}} {{out}}

[group('device')]
[doc("Profile one boot end to end on the board LG_ENV names; samples land in local/, the checkout ends on a detached HEAD")]
bootprofile:
    bench test HEAD --skip-build -- tests/diagnostics -k boot_profile -rP

[group('device')]
[doc("Pull a dated tarball of the device's /data into local/")]
kiosk-backup host=kiosk-host:
    tools/kiosk-backup.sh {{host}}
