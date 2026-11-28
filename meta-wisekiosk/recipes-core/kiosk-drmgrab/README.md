# kiosk-drmgrab

`kiosk-drmgrab_1.0.bb` builds `files/kiosk-drmgrab.c` against libdrm and installs
`/usr/bin/kiosk-drmgrab`, the half that runs on the board. Run as root, it finds the first lit CRTC's primary plane, exports the
buffer the panel is scanning out, and writes to stdout one header line
(`<width> <height> <pitch> <fourcc> <modifier>`) followed by the buffer's bytes. Any failure exits 1
with the reason on stderr and nothing on stdout.

## How it fits

- `kiosk-screenshot.py`, beside the recipe and never installed, is the half that runs on the workstation
  (`just screenshot`): it runs `kiosk-drmgrab` over SSH through `tools/kiosk-ssh.sh` and decodes the
  stream into an image. Its decoder test is `tests/applications/screenshot/test_decoder.py`.
- It opens `/dev/dri/card0` and drops DRM master at once so the browser keeps its own. It copies the
  buffer before writing, so a slow link does not hold the dma-buf.
- `kiosk-zero-w.yaml` adds the package through `IMAGE_INSTALL`; the build depends on `libdrm`.

Part of [the display](../../../docs/display.md).
