# The device

A Raspberry Pi Zero W driving one panel: one ARMv6 core (BCM2835) at up to 1 GHz, 512 MB
of RAM, WiFi on a BCM43430 over SDIO, HDMI to the panel, no battery-backed clock, and no serial
console. Everything the board runs, and the order it boots in, is shaped by three facts: it is
reached only over WiFi, a broken image needs hands on the unit to recover, and its one core is busy
through the whole of boot.

## Provisioning

The image carries no site configuration. Every site value lives outside this repository, in
`~/.config/wisekiosk/secrets.yaml` (`$KIOSK_SECRETS` overrides the path), copied from the tracked
[`secrets.yaml.tmpl`](../secrets.yaml.tmpl), which keeps every value empty: the WiFi SSID and PSK
hash, an optional `KIOSK_URL`, the hostname, the nameservers and the machine-id.
[`tools/provision.sh`](../tools/provision.sh) reads that file and writes the board's `/data/config`:

```sh
just flash /dev/sdX                 # write the card image; refuses a wrong keyring or a dirty tree
just provision-fresh-card /dev/sdX  # mount partition 4, write the site configuration, unmount
just provision-device               # the same, over ssh, for a board already reachable
```

A fresh card is provisioned before its first boot, because the WiFi credentials are the way in.
`/data` is the card's fourth partition, and nothing on the card says so. `provision-fresh-card`
derives it; provisioning a mounted partition by hand (`tools/provision.sh card <mountpoint>`) means
picking it, and picking the rootfs or the FAT boot partition leaves a board that boots with no
network and no way in but a USB keyboard. `tools/provision.sh` refuses both — FAT cannot hold the
`0600` the WiFi credentials need, and a non-root run leaves them owned by the wrong user — but only
after the card is written.

At boot, [`kiosk-provision`](../meta-wisekiosk/recipes-core/kiosk-provision/README.md) applies the
hostname, keeps the machine-id on `/data`, and seeds the app's configuration,
`/data/config/config.json`, from the image's example when there is none. Once seeded the operator
owns that file, and no update overwrites it. `wpa_supplicant`, the browser and the resolver read their
files in `/data/config` directly.

`KIOSK_URL` is optional. Unset, provisioning writes no `KIOSK_URL` line and the browser shows the
board's own app ([`display.md`](display.md) §"The launcher"); set, it points the browser at another
origin, which stays supported for debugging. A board provisioned with a remote value moves to the
local app when that line is removed from `/data/config/kiosk.conf`.

The machine-id is 32 lowercase hex characters and unique to each board: systemd derives the
network's DHCP identifier from it, so two boards sharing one collide on the LAN. Provisioning writes
it to `/data`, and each update copies it into the slot it writes ([`updates.md`](updates.md)
§"What a new slot carries"). A machine-id not recorded in `secrets.yaml` is generated, and a board
re-provisioned without it comes back with a new one.

Losing `/data` is a re-provisioning, not a restore: `tools/provision.sh` writes the site
configuration again from `secrets.yaml`. `just kiosk-backup` pulls a board's `/data` into the
gitignored `local/` for anything else worth keeping.

## Boot

U-Boot boots with no delay ([`recipes-bsp/u-boot`](../meta-wisekiosk/recipes-bsp/u-boot/README.md)),
loads the kernel from the slot it picked, and systemd brings up the rest. The core is saturated from
the kernel's start to the page, so the image carries as little as it can ahead of the network:
[`kiosk-hardware`](../meta-wisekiosk/recipes-core/kiosk-hardware/README.md) masks the units and udev
rules a kiosk with no login session, no resolver daemon and no add-on hardware does not need, and
[`classes`](../meta-wisekiosk/classes/README.md) replaces the resolver daemon with a static
`/etc/resolv.conf` pointing into `/data/config`. `kiosk-zero-w.yaml` removes from the image what
this board has no use for — Bluetooth, audio, touchscreen, the serial console, the syslog daemons
journald already covers, the hardware database, every locale but one and every time zone but the
Americas — and keeps keyboard and USB host support for the recovery console.

[`kiosk-bootprof`](../meta-wisekiosk/recipes-core/kiosk-bootprof/README.md) measures a boot, for
one boot at a time; it is not part of the image.

## Network

`wpa_supplicant` joins the site's network with the credentials on `/data`
([`recipes-connectivity/wpa-supplicant`](../meta-wisekiosk/recipes-connectivity/wpa-supplicant/README.md)).
A board without a network is a board nobody can reach, so the unit waits for the WiFi interface to
exist and restarts on failure. [`kiosk-netcheck`](../meta-wisekiosk/recipes-core/kiosk-netcheck/README.md)
withholds marking a slot good until the board has reached its LAN, which is how a slot that boots but
cannot reach the network falls back ([`updates.md`](updates.md) §"Falling back").

## Time

The board has no clock that survives power-off. `systemd-timesyncd` keeps its saved time on `/data`
([`kiosk-timesync-persist`](../meta-wisekiosk/recipes-core/kiosk-timesync-persist/README.md)) and
corrects it from NTP once the network is up. The time zone is set in the image by
`DEFAULT_TIMEZONE`, because a setting made on the board would not survive an update.

## Logs and crash records

The journal is the board's only evidence channel, and it lives on `/data`
([`kiosk-journal`](../meta-wisekiosk/recipes-core/kiosk-journal/README.md)), so the logs of a slot
that failed survive the fallback that replaces it. A reset or a panic leaves its own record in
pstore, a region of RAM that survives a reset: the kernel's console tail through the `ramoops`
overlay, and its soft-lockup detector and ftrace records through the kernel's config fragments
([`recipes-kernel/linux`](../meta-wisekiosk/recipes-kernel/linux/README.md)). The overlay is a
`config.txt` line, so a board gains it only when its card is flashed.

A panic restarts the board. Before userspace is up only the kernel command line can arrange that,
so `panic=10` is there (on `/boot`, so set when the card is flashed); once userspace is up,
`kiosk-hardware`'s sysctls panic on any oops and reboot a second later, and systemd pets the hardware
watchdog, which resets a board whose PID 1 stops answering.

## Memory

A board whose memory runs out thrashes rather than kills: code pages refault from the card and
compressed pages fill zram, so the kernel's OOM killer never runs, PID 1 starves and the watchdog
resets the board with no message. Ending that needs something inside the kernel, because whatever
starves PID 1 starves a userspace watcher too; something that sees file-page thrash, not only low
free memory; something that acts inside the 14 s watchdog window; and something an update can
deliver, without a WebKit rebuild or a write to the shared `/boot`.

`kiosk-hardware` writes `1000` to MGLRU's `min_ttl_ms`, the value the kernel's documentation names.
`kswapd`, a kernel thread starvation cannot stop, compares the age of the oldest file-page
generation with it; a younger generation means the working set is evicted faster than the limit
allows, and the kernel calls the OOM killer (`Documentation/admin-guide/mm/multigen_lru.rst`,
"Thrashing prevention"). The thrash then ends in a kill the kernel logs, which reaches the journal
and, across a reset, pstore. The browser and the backend restart on any exit, so the panel comes
back as it does after the browser is killed; a process holding memory it cannot give back is killed
repeatedly instead of the board resetting. Swap is a compressed RAM device of half the board's
memory ([`recipes-extended/zram`](../meta-wisekiosk/recipes-extended/zram/README.md)).

[`kiosk-soak`](../meta-wisekiosk/recipes-core/kiosk-soak/README.md) samples the browser's and the
system's memory, load and temperature every five minutes into `/data`, and its README says how to read a long run.

## CPU frequency

[`kiosk-cpufreq`](../meta-wisekiosk/recipes-core/kiosk-cpufreq/README.md) caps the core's
frequency below its top operating point; its README says why, and what the cap costs.

## Getting in

Root logs in over ssh with no password: the image carries `debug-tweaks`, because a board nobody can
log into is recovered only by pulling its card. That is a known gap, tracked as #7 debug-tweaks
empty root password.

With the network gone, a USB keyboard reaches a login on `tty2` ([`display.md`](display.md)
§"Consoles").

`kiosk-recover` reverses `kiosk-hardware`'s boot trims for a debugging session — it unmasks the
resolver, login and userdb units, removes the masked udev rules and restores the resolver link, then
reboots ([`kiosk-recover`](../meta-wisekiosk/recipes-core/kiosk-recover/README.md)). It lives on
`/data` as `/data/RECOVER.sh`, placed by provisioning, so it survives updates; a card flash
recreates `/data` empty, and provisioning places it again:

```sh
/data/RECOVER.sh --dry-run   # list exactly what would change; touch nothing
/data/RECOVER.sh             # apply and reboot
```

It is not a boot un-bricker: it runs on a slot that already gives a shell. A slot that does not is
an A/B fallback ([`updates.md`](updates.md) §"Falling back").
