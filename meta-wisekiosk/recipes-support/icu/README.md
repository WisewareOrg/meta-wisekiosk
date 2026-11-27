# icu

`icu_%.bbappend` shrinks ICU's data library for the target by rebuilding it with a locale filter.
`files/filter.json` is a `localeFilter` that keeps language `en` and leaves every feature category
(break iteration, collation, charset mappings) whole. The bbappend adds the file to `SRC_URI` and
`make-icudata` to `PACKAGECONFIG`, both for `class-target` only.

## How it fits

- The upstream recipe's `do_make_icudata` task rebuilds the data archive with
  `ICU_DATA_FILTER_FILE=${WORKDIR}/filter.json`; it is a no-op unless `make-icudata` is in
  `PACKAGECONFIG`, so the `SRC_URI` and `PACKAGECONFIG` lines go together.
- WebKit build-depends on ICU, so a change here rebuilds WebKit.

Part of [the image](../../../docs/image.md).

## Knobs

- Kept locales: `includelist` in `files/filter.json`.
