# openssh

`openssh_%.bbappend` uncomments the ed25519 `HostKey` line in the installed `sshd_config` and fails the
build unless exactly one `HostKey` line results. The first boot of a slot then generates one host key
instead of the three `sshd_check_keys` creates for the default list.

## How it fits

- The append runs after the upstream recipe's own, so `sshd_config_readonly` is unchanged.
- `ssh-server-openssh` comes from `EXTRA_IMAGE_FEATURES` in `kiosk-zero-w.yaml`.

Part of [the device](../../../docs/device.md).

## Knobs

- The `HostKey` path: the `sed` pattern in `do_install:append`.
