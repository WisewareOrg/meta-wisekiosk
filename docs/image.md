# How the image is built

## What a rebuild costs

BitBake rebuilds every task whose signature a change reaches, and WPE WebKit is by far the largest
of them. So what a change costs is decided by whether it reaches WebKit:

- **WebKit alone**: a change to webkit's `PACKAGECONFIG`, to a WebKit recipe, or a bump of the
  `meta-webkit` pin.
- **More than WebKit**: a change to `DISTRO_FEATURES` or `MACHINE_FEATURES`, or a bump of the `poky`
  pin, which carries WebKit's toolchain, C library and build dependencies.
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
