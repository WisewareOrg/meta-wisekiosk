# 0002 — Compile the engine through ccache by its variables, without inheriting the class

**Status:** accepted
**Decided:** 2026-11-25 (#405 Builders on one host do not share one compile cache)
**Rev:** 1

## Revisions

- **rev 1** — 2026-11-25 — first written (#405 Builders on one host do not share one compile cache).

## Context

The WPE WebKit engine is the longest compile in the image, and every change to its signature recompiles
all of it. A compile cache under `SSTATE_DIR` lets builders that share one sstate share the compiled
objects. poky's `ccache` class wires a recipe to ccache, but inheriting it appends `ccache-native` to
the recipe's `DEPENDS`; `wpewebkit.inc` already has it there, so the second append moves the engine's
task signatures.

## Decision

The engine's bbappend sets `CCACHE` and the exported `CCACHE_*` variables itself, to the values the
pinned poky's `ccache.bbclass` sets, and does not inherit the class. The variables are left out of
signatures, so a build through the cache has the same signature as one without it.

## Alternatives considered

- **`inherit ccache` in the engine recipe.** It is the supported route, but it changes the engine's
  task signatures and forces a multi-hour rebuild of every stored engine build.
- **`INHERIT += "ccache"` for every recipe.** The same signature change, for every recipe.
- **No compile cache.** Without ccache, every change to the engine's signature recompiles all of it, on
  every builder.

## Consequences

- The settings follow the pinned poky's `ccache.bbclass` by hand; a poky bump is a reason to re-read it.
- `CCACHE_DISABLE` and `bitbake -c cleanall` do not reach this cache.
- One signature names an engine built with the cache or without it, because ccache rewrites the paths it gives
  the compiler (`CCACHE_BASEDIR`), so the two builds' bytes differ.
- The design relies on `wpewebkit.inc` putting `ccache-native` in `DEPENDS`; a meta-webkit bump that drops
  it fails every compile at "ccache: not found".
- An exported `CCACHE_` setting added to the bbappend without its name in `BB_BASEHASH_IGNORE_VARS` in `kiosk-zero-w.yaml` moves the engine's
  signature: a full engine rebuild.
- Reopen if the class stops changing signatures, or a full rebuild becomes acceptable.
