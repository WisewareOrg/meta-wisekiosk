# Building WiseKiosk from source

`wisekiosk-frontend` and `wisekiosk-backend` are two halves of one application
([`tjwise99/WiseKiosk`](https://github.com/tjwise99/WiseKiosk)), built from source rather than
consumed as a release artifact. The frontend is a Svelte bundle vite emits into `/srv/kiosk`; the
backend is a Go binary that serves it and the API on `:8080`. Both require `wisekiosk-src.inc`, which
holds the one `SRCREV` both build from — there is no way to build one half at a commit the other
does not also build at.

## Bumping the app pin

Move `SRCREV` in `wisekiosk-src.inc` to the new commit — that is the whole bump. Neither
`wisekiosk-frontend/npm-shrinkwrap.json` nor `wisekiosk-backend-go-mods.inc` is committed (owner,
2026-09-27: nothing autogenerable is); `just build` and every other entry point that runs `kas`
regenerates both from the new pin, via `tools/app-lockfile.py` and `tools/go-mods.py` respectively,
before bitbake ever sees them. Both need network the first time a new pin is built; a gitignored stamp beside each output records
which commit it is for, so every later build against the same pin skips the fetch entirely. `go-mods.py`
also needs a `go` toolchain new enough for the app's `go.mod`.

A pin bump that changes the LICENSE file's contents, or removes `deploy/config.example.json`, breaks
`LIC_FILES_CHKSUM` or `wisekiosk-frontend_git.bb`'s `do_install` respectively — both fail loudly at
build time rather than silently shipping something stale.

## Codegen runs at build; nothing generated is committed here

Upstream [PR #340 generate boundary and config-type code at build instead of
committing](https://github.com/tjwise99/WiseKiosk/pull/340) removed generated code from the app's
own git history, so a bare pin bump breaks both halves' builds: `wisekiosk-frontend_git.bb`'s
`do_compile` runs `orval` and `json2ts` against the app's own OpenAPI document and JSON schema before
vite builds, and `wisekiosk-backend_git.bb`'s `do_compile` runs `go tool oapi-codegen` against the
same OpenAPI document before `go_do_compile`. Both regenerate from the pinned commit's own source on
every build, so this layer never carries a generated file that could go stale against the pin.

The backend's `go tool oapi-codegen` needs its own module graph to run, and `go build` in this recipe
stays `GOPROXY=off` — see `wisekiosk-backend-go-mods.inc`'s header and `tools/go-mods.py` for how that
closure arrives as checksummed `SRC_URI` entries instead of `go-vendor`. The owner ruled (2026-09-27)
for this shape as the most idiomatic, industry-standard approach: it is the checksummed per-module
proxy-zip layout Yocto's own `gomod://` fetcher (from styhead) and `go-mod-update-modules` (from
whinlatter) use, not available on scarthgap here, so it is written as plain
`https://proxy.golang.org/...` entries that convert mechanically once the layer moves. `go-vendor` is
what scarthgap's own tooling emits, but it is the shape Yocto replaced: for this app it would mean
vendoring every module every `go.mod` tool needs, not just oapi-codegen's own graph, and `go.sum` is
not enforced under `-mod=vendor`. Committing the generated code instead of regenerating it was rejected
outright. Those modules also carry no `LICENSE.inc` of their own, unlike upstream's own
`go-mod-update-modules`, which also generates a licences `.inc` covering every module: they build the
generator only and ship nothing in the package, so there is nothing here for a package `LICENSE` field
to account for.

## Node is held to the app's declared major

`nodejs-binary-native`'s version tracks the major the app's `package.json` `engines.node` field
declares. A pin bump that moves that major needs `nodejs-binary-native` bumped alongside it.
