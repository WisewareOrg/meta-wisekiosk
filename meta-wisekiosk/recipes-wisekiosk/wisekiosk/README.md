# wisekiosk

`wisekiosk-frontend_git.bb` and `wisekiosk-backend_git.bb` build the two halves of the application
[`WisewareOrg/WiseKiosk`](https://github.com/WisewareOrg/WiseKiosk) from source. The frontend is a Svelte
bundle that vite emits into `/srv/kiosk`, with `config.json` there a symlink to `/data/config/config.json`
and `config.example.json` under `/usr/share/wisekiosk`. The backend is a Go binary, `/usr/bin/wisekiosk`,
run by `files/wisekiosk.service` as the `kiosk` user (uid and gid 10001); it serves the bundle and the API
on `:8080`. Both recipes require `wisekiosk-src.inc`, which holds the one `SRCREV` they build from.

## How it fits

- The service orders after `network.target` and `data.mount`, wants `data.mount` (with `/data` unmounted
  it still serves and `config.json` returns 404), and restarts forever with back-off from 1 to 10 seconds.
- Site configuration lives in `/data/config`, never in the image; `kiosk-seed-config` seeds `config.json`
  from the installed example when `/data` holds none. The backend serves `/srv/kiosk` per request, so a
  file written to `/data` needs no restart.
- The frontend's generated code is not committed. `do_compile` runs `orval` and `json2ts` against the
  app's OpenAPI document and JSON schema before vite; the backend's `do_compile` runs
  `go tool oapi-codegen` against the same document before `go_do_compile`.
- Both builds run offline. The backend sets `GOPROXY=off`; `oapi-codegen` and its modules arrive as
  checksummed `SRC_URI` entries in `wisekiosk-backend-go-mods.inc`, unpacked into a `goproxy` tree. The
  frontend's npm closure arrives from `npm-shrinkwrap.json` through the `npmsw` fetcher.
- Neither `wisekiosk-backend-go-mods.inc` nor `wisekiosk-frontend/npm-shrinkwrap.json` is committed.
  `tools/go-mods.py` and `tools/app-lockfile.py` write them from the pinned commit at every `just build`
  entry, and each records the commit it was made for (a variable in the `.inc`, a gitignored `.srcrev`
  beside the shrinkwrap). Each recipe fails the parse when its file is missing or stale for `SRCREV`.
- `nodejs-binary-native` supplies node at build time ([`recipes-devtools/nodejs`](../../recipes-devtools/nodejs/README.md)).
- `SRCREV` follows the app's `main` through Renovate; see
  [`docs/security.md`](../../../docs/security.md).

Part of [the image](../../../docs/image.md).

## Knobs

- **Bumping the pin:** move `SRCREV` in `wisekiosk-src.inc`; nothing else is edited. The first build at a
  new pin needs network to regenerate the go-mods `.inc` and the shrinkwrap; later builds at that pin
  skip it. `go-mods.py` runs the Go toolchain the app's `go.mod` calls for, which Go downloads when the
  host's is older.
- **What a bump can break:** a changed `LICENSE` fails `LIC_FILES_CHKSUM` in both recipes, and a removed
  `deploy/config.example.json` fails the frontend's `do_install`; both fail at build time.
- **Node major:** `nodejs-binary-native`'s version tracks the app's `package.json` `engines.node`. A pin
  bump that moves that major needs the recipe bumped with it.
- **Service flags and restart policy:** `files/wisekiosk.service`.
- **Account ids:** `GROUPADD_PARAM` and `USERADD_PARAM` in the backend recipe; the numeric ids are what
  persist on `/data` across slots.
