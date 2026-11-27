#!/usr/bin/env python3
"""Pre-publish identity scan: keep the site out of a PUBLIC repository.

    scrub-identity.py --check [root]    exit 1 if any identifier is present
    scrub-identity.py --apply [root]    rewrite tracked files, print what changed

`--check --allow-partial` downgrades a missing map from a failure to a reported
degradation, for the one caller that cannot have the map: CI, which clones
without gitignored `local/`.

Two halves:

  PATTERN    shapes that are never legitimate here, recognised with no
             configuration: a MAC, a private IPv4, a filled-in site value, a
             board serial. Runs everywhere, including CI and a fresh clone.

  KNOWN      the literal strings in gitignored `local/device-identity.md`,
             substring-matched; catches a hostname or an SSID. The map is
             resolved through the shared git directory, so a linked worktree
             reads the primary worktree's copy.

When the map is absent the run reports PARTIAL, names the half that did not run,
and exits nonzero unless `--allow-partial` is given.

Scope is `git ls-files`.
"""
import re
import subprocess
import sys
from pathlib import Path

MAP_REL = 'local/device-identity.md'

# Keys under this namespace are recorded in the map but not scanned.
PUBLIC_NS = 'public.'

# A `key = value` line inside the map's ```identity fence; only the fence is parsed.
FENCE_OPEN = re.compile(r'^```identity\s*$')
FENCE_CLOSE = re.compile(r'^```\s*$')
MAP_ROW = re.compile(r'^\s*([A-Za-z0-9_.]+)\s*=\s*(\S.*?)\s*$')

# --- the pattern half ------------------------------------------------------
# Each entry is (label, compiled regex, remedy). A hit is a failure; there are no exemptions.
PATTERNS = [
    (
        'MAC address',
        # The all-ff broadcast and all-zero null addresses are excluded.
        re.compile(r'(?<![0-9A-Fa-f:])(?!(?:ff:){5}ff|(?:00:){5}00)'
                   r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])', re.I),
        'a MAC identifies one board and its vendor OUI; keep it in local/',
    ),
    (
        'IPv6 link-local',
        # fe80::/10 with a modified-EUI-64 interface id: the literal ff:fe marker makes it the MAC-embedding form.
        re.compile(r'(?<![0-9A-Fa-f:])fe80:[0-9A-Fa-f:]*ff:fe[0-9A-Fa-f:]+(?![0-9A-Fa-f:])', re.I),
        'a link-local IPv6 embeds the interface MAC; keep it in local/',
    ),
    (
        'private IPv4',
        re.compile(r'(?<![0-9.])(?:192\.168\.\d{1,3}\.\d{1,3}'
                   r'|10\.\d{1,3}\.\d{1,3}\.\d{1,3}'
                   r'|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![0-9.])'),
        'device addresses live in KIOSK_HOST or a local .env; `just find <cidr>` discovers one',
    ),
    (
        'filled-in site value',
        # An empty pair and a `${VAR}` reference do not match.
        re.compile(r'\b(?:WIFI_SSID|WIFI_PSK_HASH|KIOSK_URL|KIOSK_HOSTNAME|KIOSK_MACHINE_ID'
                   r'|KIOSK_NAMESERVER|MIRROR_HOST)\s*\??=\s*"(?!\s*\$\{)[^"\s][^"]*"'),
        'site configuration belongs in ~/.config/wisekiosk/secrets.yaml, never in the tree',
    ),
    (
        'board serial',
        re.compile(r'\b[Ss]erial\b\s*[:=]\s*`?[0-9a-f]{16}\b'),
        'a Pi serial identifies one physical unit; keep it in local/',
    ),
    (
        'machine-id',
        # 32 hex only beside the journal path or the word machine-id / KIOSK_MACHINE_ID, case-insensitively; {16,32} hex catches a truncated id.
        re.compile(r'(?:/var/log/journal/|(?i:machine[-_ ]?id)[^\n]{0,60}?)'
                   r'(?<![0-9A-Za-z])[0-9a-f]{16,32}(?![0-9A-Za-z])'),
        'a machine-id identifies one installed unit; keep it in local/ and cite it as <KIOSK_MACHINE_ID>',
    ),
]

# This file contains every pattern it searches for, so it is excluded from its own scan.
SELF = 'tools/scrub-identity.py'


def partial_rc(allow_partial):
    """Exit code for a scan that could not run in full."""
    if allow_partial:
        print('  (--allow-partial: the caller has declared it cannot hold the map)')
        return 0
    print(f'  FAILED -- run this where {MAP_REL} exists, or pass --allow-partial to '
          'accept a pattern-only scan.')
    return 1


def repo_root(argv_root):
    if argv_root:
        return Path(argv_root).resolve()
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                         capture_output=True, text=True, check=True).stdout.strip()
    return Path(top)


def map_path(root):
    """Where `root`'s identity map lives, resolved through the shared git dir.

    The map under `root` wins when present; otherwise the parent of
    `git rev-parse --git-common-dir` (relative to `root` from the primary tree,
    absolute from a linked one) is the primary worktree root."""
    direct = root / MAP_REL
    if direct.exists():
        return direct
    result = subprocess.run(['git', 'rev-parse', '--git-common-dir'], cwd=root,
                            capture_output=True, text=True)
    shared = result.stdout.strip()
    if result.returncode != 0 or not shared:
        return direct
    shared = Path(shared)
    if not shared.is_absolute():
        shared = root / shared
    return shared.parent / MAP_REL


def _map_rows(path):
    """[(key, real)] for path's scanned ```identity fence rows."""
    rows, inside = [], False
    for line in path.read_text(encoding='utf-8').splitlines():
        if not inside:
            if FENCE_OPEN.match(line):
                inside = True
            continue
        if FENCE_CLOSE.match(line):
            break
        m = MAP_ROW.match(line)
        if not m:
            continue
        key, real = m.group(1), m.group(2)
        if key.startswith(PUBLIC_NS) or not real:
            continue
        rows.append((key, real))
    return rows


def load_map(root):
    """[(key, real, placeholder)] for the scanned rows, or None if no map."""
    path = map_path(root)
    if not path.exists():
        return None
    return [(key, real, '<' + key.upper().replace('.', '_') + '>')
            for key, real in _map_rows(path)]


def tracked(root):
    """(relative path, text) for every tracked file that decodes as UTF-8."""
    listing = subprocess.run(['git', 'ls-files'], cwd=root,
                             capture_output=True, text=True, check=True).stdout
    for name in listing.splitlines():
        if not name:
            continue
        path = root / name
        try:
            yield name, path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue


def main():
    argv = [a for a in sys.argv[1:] if a != '--allow-partial']
    allow_partial = '--allow-partial' in sys.argv[1:]

    mode = argv[0] if argv else '--check'
    if mode not in ('--check', '--apply'):
        print(f'usage: {SELF} [--check|--apply] [--allow-partial] [root]', file=sys.stderr)
        return 2

    root = repo_root(argv[1] if len(argv) > 1 else None)

    rows = load_map(root)

    # Reaches stderr for a caller reading only the exit code, which `--allow-partial` makes 0.
    if rows is None:
        print(f'{SELF}: no {MAP_REL} reachable from {root} -- the KNOWN half '
              '(hostname, SSID, PSK hash) is INERT for this run.', file=sys.stderr)

    findings, rewritten, scanned = [], [], 0

    for name, text in tracked(root):
        scanned += 1
        new = text

        if name != SELF:
            for label, pattern, remedy in PATTERNS:
                for m in pattern.finditer(text):
                    line = text.count('\n', 0, m.start()) + 1
                    findings.append(f'{name}:{line}  {label} -- {remedy}')

        for _key, real, placeholder in (rows or []):
            if name == MAP_REL or real not in new:
                continue
            findings.append(f'{name}  known identifier ({new.count(real)}x) from {MAP_REL}')
            new = new.replace(real, placeholder)

        if mode == '--apply' and new != text:
            (root / name).write_text(new, encoding='utf-8')
            rewritten.append(name)

    half = 'PATTERN + KNOWN' if rows else 'PATTERN only'
    print(f'{len(PATTERNS)} patterns, {len(rows or [])} known values, '
          f'{scanned} tracked files scanned ({half})')

    if mode == '--apply':
        print(f'{len(rewritten)} file(s) rewritten')
        for f in rewritten:
            print(f'  {f}')
        return 0

    if findings:
        print(f'\nIDENTITY IN A TRACKED FILE ({len(findings)}) -- do not publish:')
        for f in findings:
            print(f'  {f}')
        return 1

    # A partial scan is not a clean scan.
    if rows is None:
        print(f'  PARTIAL -- no {MAP_REL}, so the KNOWN half did not run. '
              'Pattern scan found nothing; a hostname or SSID leak would not be visible here.')
        return partial_rc(allow_partial)
    if not rows:
        print(f'  PARTIAL -- {MAP_REL} has no usable rows inside its ```identity fence, '
              'so the KNOWN half scanned nothing.')
        return partial_rc(allow_partial)

    print('  clean -- no identity in any tracked file')
    return 0


if __name__ == '__main__':
    sys.exit(main())
