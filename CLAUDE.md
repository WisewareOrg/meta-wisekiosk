# Agent working rules — meta-wisekiosk

The rules an AI agent works under in this repository, and only those no other document states. What
the repository is, and the index of its documents, is the [README](README.md). The conventions and
gates are [`CONTRIBUTING.md`](CONTRIBUTING.md), injected at session start by
[`.claude/settings.json`](.claude/settings.json) up to its review checklist, which
`.claude/hooks/review-diff.py` puts in front of the model before each commit. The global agent rules
still apply.

- **All work happens in the one main checkout.** The build keys, the cache directories and the
  bench libraries are wired only there, so no worktree and no second clone.
- **A Renovate entry ahead of ours in the merge queue may be taken out, and is never put back.**
  Renovate re-queues its own.
- **Nothing irreversible is an agent's decision.** A change to the RAUC keyring or `compatible`, a
  write to `/boot`, a card flash — anything a board cannot recover from without hands on it — is
  prepared as a change for review and left to the owner.
