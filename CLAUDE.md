# Agent working rules — meta-wisekiosk

Working conventions for an AI agent in this repository. **Project facts are not here** — the
[README](README.md) says what this is and holds the only index of the repository's documents. The
gates and the review checklist are [`CONTRIBUTING.md`](CONTRIBUTING.md), injected at session start by
[`.claude/settings.json`](.claude/settings.json). This file holds only the rules layered on top,
which is why it is short: a rule stated in another document does not belong here as well.

The global rules in `~/.claude/CLAUDE.md` still apply — shell behaviour, delegation, the GitHub
conventions. Nothing here overrides them.

## What will bite you here

- **`just build`, never `kas-container` directly.** kas alone skips
  `tools/write-build-rev.sh`, so a tree that has built before builds against the *previous* commit
  and the reproducibility gate refuses the image at flash time.
- **A webkit `PACKAGECONFIG` change or a WebKit recipe edit invalidates WebKit.**
  `DISTRO_FEATURES`, `MACHINE_FEATURES`, or a poky/meta-openembedded pin bump invalidate more than
  WebKit. Either is a multi-hour rebuild — see [`README.md`](README.md) §"Quick start" for the
  measured costs — so decide before starting.
- **Every dedicated test on a board runs through the bench driver** — the rule and the form are
  [`docs/testing.md`](docs/testing.md) §"Running it".
- **Never destructively test the prod board.** It is wall-mounted and carries the live soak run;
  bench is the OTA, reboot and rollback target. Roles and addresses are in
  `local/device-identity.md` — read them, do not remember them.
  `.claude/hooks/guard.sh` blocks a prod-targeted destructive op, and it is only as good as that file.
  A `tools/prod-authorize.sh` grant lifts that block for a fixed, time-boxed set of verbs — see
  [`CONTRIBUTING.md`](CONTRIBUTING.md) §"Before you change anything".
- **The RAUC keyring and `compatible` are a one-way lock.** A deployed board refuses a bundle it
  cannot verify and a compatible that is not its own. There is no remote undo; the order in
  [`docs/rauc-key-rotation.md`](docs/rauc-key-rotation.md) is the whole mechanism.
- **`/boot` has no A/B protection.** Kernel and rootfs fall back per slot; `cmdline.txt`,
  `config.txt` and `uboot.env` are shared, so a bad write breaks both slots and needs the card
  pulled. Boot changes ship by OTA.
- **This repository is PUBLIC.** No secret value becomes a build input, and no address, hostname,
  SSID, MAC, serial or machine-id reaches a tracked file — fixtures included.
  `tools/scrub-identity.py --check` is the gate; `tools/ci-guards.sh` catches the RFC1918 half.
- **Every `.md` change passes `just verify`**, and an investigation follows
  [`docs/issue_investigation/TEMPLATE.md`](docs/issue_investigation/TEMPLATE.md) with R1-R3. Cite a
  section by name, never by line number: the named form is gated, a line number is not.

## Halt and ask

Where the tree is silent on something observable — a variable name, a partition, a service ordering,
a threshold, a new file or dependency, which board a step targets — **halt and ask** rather than
inventing it. A plausible invention reviews as normal work while encoding a choice nobody made, and
on this project the cost of a wrong choice is a physical trip to a wall-mounted unit. The same
applies to anything irreversible: a keyring change, a `/boot` write, a reflash. Produce the
inspectable form — the draft, the diff, the command — and let the owner decide.

## Review independence

Code this session wrote cannot be reviewed by this session — independence is a property of context,
not of instruction. Delegate review of your own diffs to a fresh context, handed the diff and the
spec rather than the narrative of what you did. Work you had no part in, you may review inline.
