# meta-wisekiosk

A wall-mounted Raspberry Pi Zero W kiosk: WPE WebKit straight to DRM, no desktop, no display
server. The unit shows one page and is reached only over WiFi, so everything here is shaped by the
fact that a broken image costs a physical trip to the wall.

Updates are RAUC A/B over U-Boot, delivered over the LAN. Site configuration — SSID, PSK hash, URL,
hostname, machine-id — is **never** in the image; it is written to the device's `/data` partition by
provisioning and read at runtime.

The page the kiosk shows is **WiseKiosk** ([`WisewareOrg/WiseKiosk`](https://github.com/WisewareOrg/WiseKiosk)),
and this repository builds it from source into the image — both halves, at one pinned app commit.
The backend serves the frontend's bundle over the loopback, so the display does not depend on a
remote origin being reachable. The app's configuration is the one part that is never baked: it lives
at `/data/config/config.json` on the slot-shared partition, so it survives an A/B update. If that
file is absent, `kiosk-provision` seeds it from the image's own
`/usr/share/wisekiosk/config.example.json`; once seeded, the operator owns it, and no later image
update overwrites it.

The kiosk browser unit defaults to that local app and treats `KIOSK_URL` as an optional override, so
a site can still point the browser elsewhere. Provisioning shares that default: `KIOSK_URL` in
`secrets.yaml` is optional, and [`tools/provision.sh`](tools/provision.sh) writes it into
`/data/config/kiosk.conf`, which wins over the unit, only when a site sets one — left unset, no
`KIOSK_URL` line is written at all, and the board reaches the local app through the unit's own
default. Another origin — a Docker host, say — stays supported for debugging. A board already
provisioned with a remote value is moved to the local app by editing `/data/config/kiosk.conf`
directly (#96 provisioned boards keep their old `KIOSK_URL`).

How to work in this repository — the gates, the conventions and the review checklist — is
[CONTRIBUTING.md](CONTRIBUTING.md); the rules an AI agent works under are [CLAUDE.md](CLAUDE.md).

> ## Attribution
>
> This project builds on [jsmith212/meta-autonomos](https://github.com/jsmith212/meta-autonomos),
> which supplies the `autonomos` distro, the RAUC bundle recipe and the Raspberry Pi platform layer.
> kas fetches it at a pinned commit into `sources/`; this repository contains none of it.
>
> The upstream repository carries **no top-level license**. Its core layer contains a `COPYING.MIT`
> (standard Yocto layer boilerplate) and its README defers to per-recipe licenses, so the licensing
> of the tree as a whole is unclear — all rights not clearly granted remain with its author. Nothing
> here is offered under any license on their behalf, and nothing here redistributes it — `sources/`
> is gitignored and every user fetches upstream directly from upstream.
>
> Upstream's identifiers — the `autonomos` distro, `AUTONOMOS_FEATURES`, the `meta-autonomos-*` layer
> names — are deliberately left unrenamed. Two concrete reasons: the RAUC *compatible* string is
> `autonomos-${MACHINE}`, a literal set by upstream's `autonomos-rauc.bbclass`, and a deployed board
> refuses a bundle whose compatible does not match its own — so moving off upstream's class or
> renaming its identifiers is a one-way change that strands every unit in the field. And the patch
> in `patches/meta-autonomos/` has to apply to upstream's files as upstream writes them.

## Mission

Give the WiseKiosk application a dedicated home on one board: one that shows it well, and that its
operator can set up and leave.

The appliance replaces Raspbian on this board, which performs badly there and whose support for the
board has faded. It is a vessel. What the viewer sees is the application, and everything here exists
to serve that.

- **The application, shown well.** The WiseKiosk instance is on the panel, live, and running smoothly.
- **Self-sufficient.** Everything the instance needs runs on the one board. A deployment depends on
  no other machine the operator runs.
- **Isolated.** Each appliance is its own deployment, unrelated to and unconnected with every other.
- **Easy to keep.** The operator configures, deploys and maintains it, primarily without a visit to the panel.

## Layout: scaffolding vs. layer

The repository is a project, not a layer. Exactly one directory in it is a BitBake layer.

```
meta-wisekiosk/                    <- the repository (project scaffolding)
├── README.md, CONTRIBUTING.md     what this is; how to change it and get it merged
├── CLAUDE.md                      working rules for an AI agent, and who owns which fact
├── .claude/                       session settings and hooks: the commit self-review, the
│                                  device guard and its self-test, the compaction snapshot
├── kiosk-zero-w.yaml              kas config: the one entry point
├── includes/                      repo pins and machine config, pulled in by the above
│   ├── base.yaml                  every repo + commit, incl. meta-autonomos and its patches
│   ├── rauc.yaml
│   ├── cve-audit.yaml             opt-in cve-check overlay, joined on by `just cve-build`
│   └── platforms/
│       ├── raspberrypi.yaml
│       └── raspberrypi-zero-w.yaml
├── patches/<repo>/                patches kas applies to upstream checkouts
├── meta-wisekiosk/                <- THE LAYER: recipes, bbappends, classes
│   ├── conf/layer.conf
│   ├── classes/
│   └── recipes-*/
├── Justfile, justfiles/           build, OTA and device commands
├── tools/                         provisioning, bundle delivery, device debugging, doc gate,
│                                  CI guards, the identity scan, the build-commit writer and
│                                  reproducibility gate
├── docs/                          README.md (the index), layers-and-kas.md, testing.md,
│                                  rauc-key-rotation.md, cve-and-sbom.md, layer-currency.md,
│                                  requirements/, issue_investigation/
└── sources/                       gitignored; everything kas fetches lands here
```

Nothing outside `meta-wisekiosk/` is read by BitBake. Nothing inside it is read by anything else.
If you are new to Yocto, read **[docs/layers-and-kas.md](docs/layers-and-kas.md)** — it explains what
a layer is, what kas does with these files, and why meta-autonomos's patch cannot be a bbappend.

Every change that was acted on is documented at the recipe carrying it; the per-issue investigations
behind those changes are indexed in **[docs/README.md](docs/README.md)**.

## Quick start

`kas-container` runs the build inside a container, so a working **Docker** is a
prerequisite. The flash and OTA paths additionally need `git`, `debugfs` (`e2fsprogs`) and `openssl`,
and the repository guards (`just guards` and the pre-commit hook) and the layer-currency recipes
(`just currency`, `just gap`) need **PyYAML** to read the kas YAML, and the guards' lint of the tests'
Python needs the pinned **ruff**, **interrogate** and **pydoclint** — all of them refuse rather than
skip when one is missing. `uv sync` installs all four, pinned in `pyproject.toml`/`uv.lock`, into
`.venv/` at the repository root — the single install path, no PEP-668 workaround needed.

A **`.venv/` at the repository root is used automatically** where it exists, by the Justfile and by
`tools/ci-guards.sh` alike — neither `just` nor a git hook sources a shell startup file, so a venv
is never on `PATH` and a bare `python3` would take a host interpreter that may have no PyYAML. No
activation is needed. Only the lint of the tests' Python requires the venv; everything else falls back
to `python3` without one.

```sh
curl -L -o ~/bin/kas-container https://raw.githubusercontent.com/siemens/kas/5.4/kas-container
chmod +x ~/bin/kas-container

mkdir -p ~/.config/wisekiosk
cp secrets.yaml.tmpl ~/.config/wisekiosk/secrets.yaml   # fill in; lives OUTSIDE this public repo
```

**One-time host setup: the shared hash-equivalence server.** Every `tools/kas-run.sh` build,
including the fresh-clone `just build` below, refuses to start without it — one
`bitbake-hashserv` on the host, not one database per build directory, Yocto's own documented
deployment (the dev manual's "Setting up a Hash Equivalence Server"). A `--user` service runs
without a login session only with linger enabled, which the hash server and, on the bench host,
`bench run`'s own timer both need:

```sh
loginctl enable-linger "$USER"
```

Read the `poky` `url:` and `commit:` from [`includes/base.yaml`](includes/base.yaml), then:

```sh
mkdir -p ~/.local/share/bitbake-hashserv
git clone --no-checkout <poky url> ~/.local/share/bitbake-hashserv/poky
git -C ~/.local/share/bitbake-hashserv/poky checkout --detach <poky commit>
mkdir -p ~/.config/systemd/user
```

Write this to `~/.config/systemd/user/bitbake-hashserv.service`:

```ini
[Unit]
Description=BitBake hash equivalence server shared by every build on this host

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/.local/share/bitbake-hashserv/poky/bitbake/bin/bitbake-hashserv --bind unix://%h/.local/share/bitbake-hashserv/hashserv.sock --database %h/.local/share/bitbake-hashserv/hashserv.db
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

```sh
systemctl --user daemon-reload
systemctl --user enable --now bitbake-hashserv.service
```

The server listens on `~/.local/share/bitbake-hashserv/hashserv.sock`;
`tools/kas-run.sh` mounts `~/.local/share/bitbake-hashserv` read-only at `/hashserv` inside
the build container.

```sh
just build          # kas fetches sources/, applies the patches, builds core-image-base and deploys kiosk-bootprof
```

Builds on one host take turns: a second `just build`, or any other `tools/kas-run.sh` call except an
interactive `just shell`, waits for the first and says which build holds the host. The turn is held
by `kas-container` and its docker client, not by the build container: killing both frees it while
that container may still be building.

**The version in that `curl` URL is the kas version the build uses, and it changes nothing on its
own.** `just build` runs whatever `kas-container` sits in `~/bin`; nothing downloads it but that
`curl`. Renovate opens a pull request when kas releases and automerges it through the merge queue,
gated by `bench run`'s build of the queued commit ([`docs/testing.md`](docs/testing.md)
§"Running it"); merging is the moment to re-run the `curl` and a full build. A new kas is a new
build container, with a newer host distro that can break a build hours in.
`kas-container --version` shows what is installed.

`just build` writes `meta-wisekiosk/conf/build-rev.inc` (the commit being built, see
[what commit an image was built from](docs/layers-and-kas.md#what-commit-an-image-was-built-from))
and then runs `kas-container build kiosk-zero-w.yaml`. Calling `kas-container` directly skips the
first half: on a fresh clone bitbake refuses to parse, and on a tree that has built before it builds
against the *previous* run's commit — which the gate then refuses at flash. The first run clones
every repo declared across the kas include chain — `includes/base.yaml`, `includes/rauc.yaml` and
`includes/platforms/raspberrypi.yaml` — into `sources/`: several GB and a long while before any
compiling starts.

A change to webkit's `PACKAGECONFIG`, to a WebKit recipe, or **a bump of the meta-webkit pin**
invalidates WebKit alone. A change to `DISTRO_FEATURES`, to `MACHINE_FEATURES`, or **a bump of the
poky or meta-openembedded pin** invalidates more than WebKit. Either is a multi-hour rebuild — see
[cold build time](docs/issue_investigation/cold_build_time/README.md) for the measured costs, which
are of the WebKitGTK image, and the host they were measured on. Make those decisions before
starting, not after. `config.txt`-only knobs (`GPU_MEM`, HDMI, overscan, UART) are free to change,
and so is the kernel's `PREFERRED_VERSION` — the kernel is outside webkit's dependency closure.
Cheap to rebuild is not the same as reaching a board: the `config.txt` knobs are on the shared FAT
partition RAUC never writes — see
[gpu compositing](docs/issue_investigation/gpu_compositing/README.md) §"Delivery and board".

Every target recipe compiles through poky's `ccache` class and keeps its cache under `SSTATE_DIR`
(`CCACHE_TOP_DIR`), bounded per recipe by `CCACHE_MAXSIZE` in [`kiosk-zero-w.yaml`](kiosk-zero-w.yaml),
so every builder that shares one sstate shares it. `CCACHE_DISABLE = "1"` for a recipe turns its
cache off. `bitbake -c clean` leaves the store; `bitbake -c cleanall` (`do_cleanccache`) empties a
recipe's store for every builder, and its next build is then a full compile.

### Flashing a card

```sh
just flash /dev/sdX                 # writes build/.../*.wic.bz2, re-reads the partition table
just provision-fresh-card /dev/sdX  # mounts partition 4, writes the site config, unmounts
```

`flash` refuses an image not baking the fleet signing keyring, or one mixing builds: a wrong keyring
is repairable only by another reflash. It also refuses, with no override, a build from a dirty or
unpushed tree, or one whose `/etc/buildinfo` does not name the current HEAD — see
[what commit an image was built from](docs/layers-and-kas.md#what-commit-an-image-was-built-from).
Provision before first boot — WiFi credentials are the way in.

`/data` is the **fourth** partition, and nothing on the card says so — the layout is boot, rootfs-a,
rootfs-b, data. `provision-fresh-card` derives it; provisioning by hand instead
(`tools/provision.sh card <mountpoint>`) means picking that partition yourself, and picking the
rootfs or the vfat boot partition leaves a unit that boots with no network and no way in but a USB
keyboard. `tools/provision.sh` refuses either — vfat cannot hold the 0600 the wifi credentials need,
and a non-root run leaves them owned by the wrong uid — but only after the card is already written.

### Updating a running device

```sh
just kiosk-ota      # bundle -> preflight -> stream -> rauc install
just kiosk-reboot
just kiosk-rollback # if the new slot comes up wrong
```

Every recipe that defaults to a device — `kiosk-ota`, `kiosk-install`, `kiosk-reboot`,
`kiosk-rollback`, `kiosk-preflight`, `kiosk-backup`, `provision-device` — takes its default from one
`kiosk-host` variable in the [`Justfile`](Justfile), so `export KIOSK_HOST=root@<addr>` retargets all
of them at once. Boards get swapped on this unit; `just find <cidr>` is how you learn the address of
the one now on the bench. An explicit `host` argument still wins over both. The install also
captures what the board does while the slot is written, and what a reset left behind — its header
in [`tools/kiosk-install.sh`](tools/kiosk-install.sh) says what.

`kiosk-preflight` refuses a delivery that cannot work — wrong slot size, stale bundle — before the
install. Every recipe that puts software on a board also refuses, with no override, a build from a
dirty or unpushed tree, so a build shipped from this host is always one someone else can check out;
tying a bundle to the rootfs inside it is #48 bundle-image-tie.

Every install, by hand, by `tools/rauc-rotate.sh` or by a test, goes through
[`tools/kiosk-install.sh`](tools/kiosk-install.sh), and the board streams the bundle;
[the bundle recipe's README](meta-wisekiosk/recipes-core/bundles/README.md) says how and why.

## Configuration and secrets

Every device-specific value lives **outside this repository**, in `~/.config/wisekiosk/secrets.yaml`
(override the path with `$KIOSK_SECRETS`): WiFi SSID and PSK hash, kiosk URL, hostname, mirror host,
machine-id. `tools/provision.sh` reads that file and writes `/data/config` on the card or on a
reachable device; the device reads it at boot.

The tracked `secrets.yaml.tmpl` carries names with empty values only. `tools/ci-guards.sh` — run by
CI and by the pre-commit hook — rejects a `secrets.yaml` at the repository root (the only place kas
would pick one up), and fails if any of those value names becomes a build input again in the kas
config, the layer, `includes/` or `patches/`. Install the hook with `just install-hooks`.

**kas merges `local_conf_header` by block name and the top-level file wins**, so a block named the
same as one in `kiosk-zero-w.yaml` is discarded silently — no warning, no error, variables that never
reach bitbake. Keep the keys unique.

Losing `/data` is a re-provisioning, not a restore. `tools/provision.sh` writes the site config
again from `secrets.yaml`, and a machine-id not recorded there comes back as a new one; there is no
multi-GB image to put back.

## Recovery

`kiosk-recover` reverses `kiosk-hardware`'s boot trims for a debugging session: it unmasks the DNS
resolver, login/session and userdb units, deletes the masked udev rule symlinks, restores the
`/etc/resolv.conf` symlink into `/data`, and reboots.

It is **not a boot un-bricker**: it runs on a slot that already gives a shell; a slot that does not is
an A/B rollback (`just kiosk-rollback`). It is idempotent, touches neither `/boot`, `sshd`, networkd
nor `wpa_supplicant`, has no timer/deadman/auto-revert, and leaves `zram.service` masked (issue #17:
that mask is a defect workaround, not a trim).

It lives on **`/data`** (placed at `/data/RECOVER.sh` by `tools/provision.sh`; source in the
[`kiosk-recover`](meta-wisekiosk/recipes-core/kiosk-recover/) recipe), so it survives an A/B flip and
a reflash. On the device:

```sh
/data/RECOVER.sh --dry-run   # list exactly what would change; touch nothing
/data/RECOVER.sh             # apply and reboot
```

Run `--dry-run` first to confirm targeting.

## Upstream fixes

One change to upstream cannot be expressed from a downstream layer and lives as a patch in
`patches/meta-autonomos/`, its header recording why it cannot be a bbappend and whether it is
suitable to submit upstream:

**The wpa-supplicant bbappend baked WIFI_SSID and WIFI_PSK_HASH into the image.** One image per
site, and the site's wireless credentials inside every update bundle.

Two more fixes belong upstream but did not need a patch, because a downstream layer can express them:

- **`wpa_supplicant.service` gives a coin-flip boot on slow WiFi firmware.** No ordering, no
  `Restart`, `Type=forking`: if it fires before the driver has created `wlan0` it exits and never
  retries, and that boot has no network at all. Addressed here with a drop-in
  (`After=sys-subsystem-net-devices-wlan0.device`, `Restart=on-failure`) plus an absolute
  `ExecStart` — systemd rejects the relative path upstream ships.
- **`git://` repo URLs no longer resolve.** `git.openembedded.org` and `git.yoctoproject.org` sit
  behind Cloudflare, which fronts HTTP/HTTPS only and refuses port 9418. `includes/base.yaml` uses
  `https://`.

## Status

**Working.** Boots, joins WiFi, renders the kiosk page on the real hardware — verified on a Pi Zero W
(BCM2835, ARMv6, 512 MB).

| | |
|---|---|
| Engine | WPE WebKit, the version the meta-webkit pin in `includes/base.yaml` carries; `ENABLE_JIT=OFF`, `USE_WOFF2=ON`, `MinSizeRel` |
| Browser | `kiosk-browser`, a small C launcher on WPE's platform API with a systemd watchdog ([ADR 0001 rev 2](docs/decisions/0001-wpe-webkit-on-drm-with-our-own-launcher.md)) |
| Display | WPE's DRM platform on vc4 firmware KMS, in the mode `video=` in the kernel's `panel-mode.cfg` sets, mesa for EGL, no display server |
| Update | RAUC A/B over U-Boot — both slots visible |

### Known gaps

- **Issue #6 RAUC signing private key is committed in this public repository** — closed by rotation;
  history keeps the dev key and purging it undoes nothing. Its replacement, the WiseKiosk 2026 key,
  is uncommitted in gitignored `local/` — back it up, git cannot. [rotation](docs/rauc-key-rotation.md)
- **Root login is unauthenticated.** The image carries `debug-tweaks`, so root has an empty password.
  Deferred deliberately while a second device still depends on unauthenticated access; tracked as
  issue #7 debug-tweaks empty root password, which carries the detail.
- **Screen blanking is checked by the kernel's own report of the screen's power and the console's
  blanking timeout, not by watching a long idle.** TST007<!-- Display blanking disabled --> reads both
  on every queue job. A panel that powers itself down is not covered.
- **The image's packages are scanned for CVEs only when somebody asks.** The scan is a manual opt-in
  audit build on a build host, and nothing detects that the last one was months ago. Deciding which
  finding matters is manual too. [CVE and SBOM](docs/cve-and-sbom.md)
