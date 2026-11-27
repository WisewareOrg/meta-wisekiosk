# nodejs

`nodejs-binary-native_26.10.0.bb` is a native-only recipe that unpacks the official Node.js tarball for
the build host (`x64` or `arm64`, mapped from `BUILD_ARCH`) into the native sysroot. Node is a build-host
tool here: it runs vite, orval and json-schema-to-typescript for the frontend and never reaches the
device.

## How it fits

- `wisekiosk-frontend` names this recipe in `DEPENDS`
  ([`recipes-wisekiosk/wisekiosk`](../../recipes-wisekiosk/wisekiosk/README.md)).
- It does not set `PROVIDES = "nodejs-native"`; meta-openembedded provides that name.
- The major version (26) follows the app's `engines.node` field. `UPSTREAM_CHECK_REGEX` pins the version
  check to that major.
- `do_install` copies `bin`, `include`, `lib` and `share` whole so the relative `npm` and `npx` symlinks
  keep resolving.

Part of [the image](../../../docs/image.md).

## Knobs

- The version: the recipe filename, with the per-architecture `SRC_URI[...].sha256sum` lines taken from
  `https://nodejs.org/dist/v<version>/SHASUMS256.txt`.
- `UPSTREAM_CHECK_REGEX`: the major the update check follows.
