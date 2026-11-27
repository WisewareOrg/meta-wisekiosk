# kiosk-netcheck

`kiosk-netcheck_1.0.bb` installs `/usr/bin/kiosk-netcheck` and `kiosk-netcheck.service`. The service
is a oneshot ordered `Before=boot-complete.target` and `RequiredBy` it; `rauc-mark-good.service`
requires that target. The script waits up to `DEADLINE` seconds for the default gateway of `IFACE`
to answer a ping. If it does, it exits 0 and, when `/data` is mounted, records that the booted slot
reached the network. If it does not, a non-zero exit leaves the target unreached, so the slot is
not marked good, the U-Boot boot counter is not reset, and three such boots drop the slot from
`BOOT_ORDER`.

## How it fits

- The proof is `/data/kiosk-netcheck/reached.<bootname>`, holding the slot's RAUC bundle hash, so it
  lapses when the slot is rewritten. A slot written by the card flash has no bundle hash and is
  never proven.
- It never marks a slot bad. With no LAN it exits 1 (withholds) only when another slot is good. It
  also restarts the boot, once, when the booted slot has never reached the network and that good
  fallback has. It exits 0 and lets the slot be marked good when no good fallback is known or the
  RAUC status cannot be read.
- It depends on `rauc`, `libubootenv-bin` (`fw_printenv`) and busybox (`ip`, `ping`).

Part of [the device](../../../docs/device.md).

## Knobs

`/data/kiosk-netcheck.conf`, sourced by the script, may set plain `NAME=value` lines
(`files/kiosk-netcheck.conf.example` shows the format):

- `DEADLINE`: seconds to wait for the LAN; default 120.
- `IFACE`: interface whose default route names the gateway; default `wlan0`.
- `TARGET`: a host to ping instead of the gateway; empty by default. An unroutable address
  exercises the no-LAN branch while the real network stays up.
