# How the image is built

BitBake builds the image; kas tells it what to build from. [`kiosk-zero-w.yaml`](../kiosk-zero-w.yaml)
is the one entry point, `just build` the one command, and this repository's own layer,
`meta-wisekiosk/`, sits on top of pinned upstream layers. This document is written for someone who
has not used Yocto: it assumes you know what a compiler and a package are, and nothing else.

## Layers

A **layer** is a directory with a `conf/layer.conf` in it. Inside it:

- `recipes-<category>/<name>/<name>_<version>.bb` — a **recipe**, the instructions for building one
  piece of software.
- `recipes-<category>/<name>/<name>_%.bbappend` — a **bbappend**, a fragment that adds to a recipe
  another layer defines. BitBake parses the `.bb`, then every `.bbappend` that matches its name in
  layer-priority order. The `%` matches any version.
- `classes/*.bbclass` — logic a recipe or the image can `inherit`.
- side directories such as `files/`, holding the loose files a recipe installs.

The image is the union of every enabled layer. `meta-wisekiosk/` holds both kinds: the `kiosk-*`
recipes are this repository's own, and the bbappends adjust software that poky, meta-raspberrypi or
meta-autonomos already package. A recipe that fails is this repository's code; a bbappend that fails
usually means the upstream recipe under it changed. Each module of the layer has a README of its own,
listed in [`../README.md`](../README.md) §"Documentation".

Nothing in this repository outside `meta-wisekiosk/` is a layer, and BitBake reads none of it.

### Layer priority

`meta-wisekiosk/conf/layer.conf` sets `BBFILE_PRIORITY_wisekiosk = "10"`. Upstream's
`autonomos-core` is 6, `autonomos-raspberrypi` 7 and the Raspberry Pi BSP layer `raspberrypi` 9 —
collection names, which `bitbake-layers show-layers` prints and which drop the `meta-` of the
directory names. Higher wins:

- where two layers carry a `.bb` for one recipe at one version, the higher layer's file is used;
- where two layers carry a `.bbappend` for one recipe, both apply, this layer's last;
- `FILESPATH`, the search order for `file://` entries in `SRC_URI`, follows the same order, so a
  file present in both layers resolves to this layer's.

Priority settles conflicts only; every enabled upstream layer still does its work.

## What kas does

`kas-container build kiosk-zero-w.yaml`, which `just build` runs, does this in order:

1. **Reads the config chain.** `kiosk-zero-w.yaml` includes `includes/base.yaml`, which includes
   `includes/rauc.yaml`; `includes/platforms/raspberrypi-zero-w.yaml` includes
   `includes/platforms/raspberrypi.yaml`. kas merges them; dictionaries merge key by key, which is how
   `includes/platforms/raspberrypi.yaml` adds a second layer to the `meta-autonomos` repository that
   `includes/base.yaml` declares.
2. **Clones every entry under `repos:`** into the gitignored `sources/`, each at its pinned `commit:`.
3. **Applies patches** a repository entry lists under `patches:`.
4. **Writes `build/conf/bblayers.conf`** from each repository's `layers:` key. A repository with no
   `layers:` key contributes its own root as one layer.
5. **Writes `build/conf/local.conf`** from `machine:`, `distro:` and every `local_conf_header:`
   block, concatenated — ordinary BitBake assignments.
6. **Runs `bitbake core-image-base kiosk-bootprof`**, the `target:`.

`kas-container checkout kiosk-zero-w.yaml` stops after the fifth step, which is the fast way to see
what a config change produced.

**kas merges `local_conf_header` by block name, and the top-level file wins.** A block named the
same as one in another file of the chain is discarded with no warning, and its variables never reach
BitBake. Every block name is unique across the chain, and a site's `secrets.yaml` is held to the same
rule.

## The pinned repositories

Every upstream repository is pinned by commit: a floating branch would make a rebuild's difference
unattributable. The pins live in three files — most in `includes/base.yaml`, meta-rauc in
`includes/rauc.yaml`, and meta-raspberrypi, meta-lts-mixins and meta-rauc-community in
`includes/platforms/raspberrypi.yaml`; `grep -rn 'commit:' includes/` lists them. Renovate proposes
each bump ([`security.md`](security.md) §"Pin currency" says how, and how far behind a pin is).

`meta-autonomos` supplies the `autonomos` distro (systemd as init, the ext4 sizing), the
`autonomos-rauc.bbclass` that sets the RAUC *compatible* string, the RAUC bundle recipe, and the
Raspberry Pi platform layer. `includes/base.yaml` declares it with its `meta-autonomos-core` layer
and the patch below; `includes/platforms/raspberrypi.yaml` adds `meta-autonomos-raspberrypi`. Its
identifiers are not renamed, for the reason in [`updates.md`](updates.md) §"The one-way lock".

Fetches use `https://`: `git.openembedded.org` and `git.yoctoproject.org` sit behind a proxy that
serves HTTP and HTTPS only and refuses the `git://` port.

### Bumping a pin

1. Edit the `commit:` in its include file.
2. `kas-container checkout kiosk-zero-w.yaml`. kas re-clones and re-applies every patch; a patch that
   does not apply fails here, which means upstream touched a patched file.
3. Regenerate such a patch against the new upstream commit with `git format-patch` into
   `patches/<repo>/`, keeping its header's reason and upstream status.
4. Run `just guards`.

A bump of poky to a new release series also moves the hash-equivalence server's own clone (below):
check it out at the new pin and restart `bitbake-hashserv.service` before building against it.

## Changes to upstream

One change cannot be expressed from a downstream layer and is a patch,
`patches/meta-autonomos/0002-wpa-supplicant-stop-baking-credentials.patch`. Upstream's
`wpa-supplicant_%.bbappend` writes `WIFI_SSID` and `WIFI_PSK_HASH` into `/etc/wpa_supplicant.conf` at
build time, which makes one image per site and puts that site's wireless credentials in every update
bundle. A bbappend of this layer cannot undo it: bbappend bodies concatenate, so a second one runs
after upstream's, never instead of it, and `BBMASK` on the file would also drop the configuration
file it installs. The patch turns that body into a no-op, and its header records whether it suits
upstream.

Every other change is a bbappend or a file this layer shadows. The general escape hatch for "the
recipe is fine but one of its input files is wrong" is `FILESEXTRAPATHS:prepend`: its directory is
searched ahead of the recipe's own, so a `file://` name the recipe asks for resolves to this layer's
copy, and the recipe never changes. The Wi-Fi unit is shadowed that way
([`recipes-connectivity/wpa-supplicant`](../meta-wisekiosk/recipes-connectivity/wpa-supplicant/README.md)).
A shadowed file is invisible in the recipe being read; after a change near the Wi-Fi unit, the
built rootfs is the thing to read:

```sh
debugfs -R "cat /etc/systemd/system/wpa_supplicant.service" \
  build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/core-image-base-raspberrypi0-wifi.rootfs.ext4
```

## The WiseKiosk application

The image builds the application from source, both halves at one pinned commit
([`recipes-wisekiosk/wisekiosk`](../meta-wisekiosk/recipes-wisekiosk/wisekiosk/README.md)), with
the Node.js the frontend build runs on supplied by
[`recipes-devtools/nodejs`](../meta-wisekiosk/recipes-devtools/nodejs/README.md). The build stays
offline and reproducible from that pin:

- The backend builds with `GOPROXY=off` and enforces its own `go.sum`. The one Go tool the build
  runs, `oapi-codegen`, arrives with its module closure as checksummed `SRC_URI` entries in
  proxy-zip layout, the layout Yocto's `gomod://` fetcher uses in later releases.
- The frontend's npm closure arrives from the app's own shrinkwrap through the `npmsw` fetcher.
- The API client, types and config types are generated from the pinned commit's own OpenAPI
  document and schemas on every build, so nothing generated can go stale against the pin.
- The Go module list and the shrinkwrap are derived from the pin, so they are not committed:
  `tools/go-mods.py` and `tools/app-lockfile.py` write them at every build entry, gitignored, and the
  recipes refuse to parse when either is missing or written for another commit.

## Setting up a build host

`kas-container` runs the build in a container, so a working Docker is the first prerequisite. The
flash and update paths also need `git`, `debugfs` (`e2fsprogs`) and `openssl`. The repository's own
Python tooling — PyYAML for the guards and the currency reports, and the pinned ruff, interrogate
and pydoclint for the lint of the tests — installs with `uv sync` into `.venv/` at the repository
root, pinned in `pyproject.toml` and `uv.lock`. The Justfile and `tools/ci-guards.sh` use that
`.venv` when it exists, since neither `just` nor a git hook reads a shell startup file; each tool
refuses rather than skips when its prerequisite is missing.

```sh
curl -L -o ~/bin/kas-container https://raw.githubusercontent.com/siemens/kas/5.4/kas-container
chmod +x ~/bin/kas-container
```

The version in that URL is the kas the build uses; `just build` runs whatever `kas-container` sits
in `~/bin`. Renovate proposes a kas release like any other pin; when one merges, re-run the `curl`
and a full build, because a new kas is a new build container. `kas-container --version` shows what
is installed.

**The shared hash-equivalence server.** `tools/kas-run.sh` refuses to start without one
`bitbake-hashserv` per host, shared by every build on it (the Yocto manual's "Setting up a Hash
Equivalence Server"). A `--user` service runs without a login session only with linger enabled:

```sh
loginctl enable-linger "$USER"
mkdir -p ~/.local/share/bitbake-hashserv ~/.config/systemd/user
git clone --no-checkout <poky url> ~/.local/share/bitbake-hashserv/poky
git -C ~/.local/share/bitbake-hashserv/poky checkout --detach <poky commit>
```

with the `poky` `url:` and `commit:` from [`includes/base.yaml`](../includes/base.yaml), and this as
`~/.config/systemd/user/bitbake-hashserv.service`:

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

`tools/kas-run.sh` mounts `~/.local/share/bitbake-hashserv` read-only at `/hashserv` in the build
container.

## Building

```sh
just build    # kas fetches sources/, applies the patches, builds core-image-base and kiosk-bootprof
```

`just build` runs [`tools/kas-run.sh`](../tools/kas-run.sh), which writes the build inputs derived
from the tree — the build stamp below, the Go module list and the shrinkwrap — and then runs
`kas-container`. Calling `kas-container` directly skips the writers: on a fresh clone BitBake refuses
to parse, and on a tree that has built before it builds against the previous run's commit, which the
reproducibility gate then refuses.

The first build clones every repository in the chain into `sources/`, several GB, before any
compiling starts. Builds on one host take turns: a second `tools/kas-run.sh` call, other than an
interactive `just shell`, waits and says which build holds the host. The turn is held by
`kas-container` and its docker client, not by the build container, so killing both frees it while
that container may still be building.

Every target recipe compiles through poky's `ccache` class and keeps its cache under `SSTATE_DIR`,
bounded per recipe by `CCACHE_MAXSIZE` in `kiosk-zero-w.yaml`, so builders that share an sstate
share it. `CCACHE_DISABLE = "1"` turns it off for a recipe; `bitbake -c cleanall` empties a recipe's
store for every builder.

`kiosk-zero-w.yaml` inherits `buildhistory`, so a branch whose `poky` pin is behind the host's last
build fails on a package version going backwards, and leaves buildhistory so the next build on the
newer pin fails too. Merge `origin/main` into such a branch before building it.

## What a rebuild costs

BitBake rebuilds every task whose signature a change reaches, and WPE WebKit is by far the largest
of them. So what a change costs is decided by whether it reaches WebKit's dependency closure —
WebKit itself or anything it builds against. The common cases:

- **WebKit alone**: a change to webkit's `PACKAGECONFIG`, to a WebKit recipe, or a bump of the
  `meta-webkit` pin.
- **WebKit and what it builds against**: a change to `DISTRO_FEATURES` or `MACHINE_FEATURES`; a
  bump of the `poky` pin, which carries WebKit's toolchain, C library and build dependencies; a
  change to systemd, which WebKit links for its journald logging (so a `systemd_%.bbappend` is never
  cheap); and a change to ICU's data
  ([`recipes-support/icu`](../meta-wisekiosk/recipes-support/icu/README.md)).
  [`renovate.json`](../renovate.json) groups the `poky` and `meta-webkit` bumps into one pull request
  so the two ride one rebuild; `meta-openembedded` reaches WebKit through one leaf, `brotli`, and
  moves on its own.

Either is a rebuild of hours on a build host, so it is decided before starting, not discovered
afterwards. `kiosk-zero-w.yaml` holds WebKit's own build levers: no debug information
(`DEBUG_FLAGS:remove:pn-wpewebkit`) and its own `PARALLEL_MAKE`.

Cheap to rebuild is not the same as reaching a board. The `config.txt` knobs (`GPU_MEM`, HDMI,
overscan, UART) and the kernel's `PREFERRED_VERSION` are outside WebKit's dependency closure and
rebuild quickly, but `config.txt` sits on the partition an update never writes:
[`updates.md`](updates.md) §"The shared /boot".

## What commit an image was built from

Every slot carries `/etc/buildinfo`, written by poky's `image-buildinfo` class
(`INHERIT += "image-buildinfo"`). The class asks git for each layer's branch and revision;
`meta-wisekiosk` is a subdirectory of this repository, so its line names this repository's HEAD:

```
meta-wisekiosk    = <branch>:<sha>
```

`grep ^meta-wisekiosk /etc/buildinfo` on a board names the source that built it.

`image-buildinfo` reads git inside `do_image` but hashes nothing it read, so a commit that touches
only docs or tooling would replay the previous build's stamp.
[`kiosk-buildinfo-cachesafe`](../meta-wisekiosk/classes/README.md) puts the commit in
`do_image[vardeps]`: a moved HEAD gives `do_image` a new signature, so `do_image`,
`do_image_ext4` and `do_image_complete` regenerate while `do_rootfs`, where the hours are, stays
cached. The commit is resolved on the host by
[`tools/write-build-rev.sh`](../tools/write-build-rev.sh), which `tools/kas-run.sh` and
`tools/rauc-rotate-build.sh` run before their own `kas-container` call, and read as a plain
assignment from the gitignored `meta-wisekiosk/conf/build-rev.inc`. Nothing is computed at parse
time, so every parse in every context reads the same bytes, and a build with no stamp fails the parse
with the class's own message. The class is reached through `IMAGE_CLASSES`, a deferred inherit, so
its append lands after `image.bbclass`'s on the same flag; `bitbake-dumpsig` on `do_image` shows
`KIOSK_BUILDINFO_REV` as its own entry with the host's commit as its value.

## The reproducibility gate

The stamp is a record: the class never fails a build, and writes `<unknown>` when git errors. The
guarantee is [`tools/reproducibility-gate.sh`](../tools/reproducibility-gate.sh), which every recipe
that puts an image on a board calls, and which refuses, with no override, unless:

- the working tree is clean by `git status --porcelain`, untracked files included — an untracked `.bb`
  is picked up by `BBFILES` and ships while the layer reads clean;
- HEAD is reachable from some ref on `origin`. It never fetches, and an unreachable `origin` refuses,
  because offline cannot be told from never pushed;
- where the caller holds the rootfs (`flash`, `kiosk-preflight`), `/etc/buildinfo` names a 40-hex
  commit equal to HEAD. A `.raucb` cannot be read with `debugfs` and nothing binds one to a rootfs
  (#48 kiosk-preflight assumes the bundle packages the checked image), so the bundle-shipping recipes
  enforce the first two.

CI checks the tree but never builds an image. The bench runner builds every merge-queue entry and
runs the same gate on the rootfs before anything is installed ([`testing.md`](testing.md)), and a
card or a bundle shipped by hand passes the gate at the moment it ships, so an image on a board is
always one someone else can check out.
