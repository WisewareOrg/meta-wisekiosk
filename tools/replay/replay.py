#!/usr/bin/env python3
"""Serves a committed replay set byte for byte. No code path here, nor in proxy.py, ever opens a
connection to anything but the client already holding the tunnel; tools/replay/README.md owns the
manifest, response-file and CA facts this tool reads.

    tools/replay/replay.py --set <dir> --port <n> --ca <dir> --log <file>
"""
import functools
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

import proxy


def respond(manifest, set_dir, method, host, port, target, headers, body, wfile, logf):
    """Writes manifest's committed response for (method, host, target) byte for byte, or a 502
    on any miss: no entry, no response file, or a file whose bytes no longer match its hash."""
    entry = proxy.decide(manifest.get("responses", {}), method, host, target)
    key = proxy.match_key(method, host, target)
    if entry is None:
        wfile.write(proxy.BAD_GATEWAY)
        wfile.flush()
        proxy.log_line(logf, f"MISS {key}")
        return
    try:
        data = (set_dir / "responses" / entry["file"]).read_bytes()
    except OSError:
        wfile.write(proxy.BAD_GATEWAY)
        wfile.flush()
        proxy.log_line(logf, f"MISS {key} (no response file {entry['file']})")
        return
    if not proxy.hash_matches(data, entry["sha256"]):
        wfile.write(proxy.BAD_GATEWAY)
        wfile.flush()
        proxy.log_line(logf, f"MISS {key} (manifest hash mismatch)")
        return
    wfile.write(data)
    wfile.flush()
    proxy.log_line(logf, f"HIT {key} sha256={entry['sha256']}")


def main():  # pragma: no cover -- CLI wiring over respond()/proxy.serve(), both proven above and by the host-only proof
    parser = ArgumentParser(description=__doc__, formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument("--set", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--log", required=True)
    args = parser.parse_args(sys.argv[1:])

    set_dir = Path(args.set)
    ca_dir = Path(args.ca)
    manifest_path = set_dir / proxy.MANIFEST_NAME
    try:
        manifest = proxy.load_manifest(manifest_path)
        proxy.check_expiry(manifest["expires"])
    except (OSError, ValueError, KeyError, proxy.ReplaySetExpired) as exc:
        sys.exit(str(exc))
    stale = proxy.stale_leaves(ca_dir, proxy.known_hosts(manifest))
    if stale:
        sys.exit("leaf cert(s) missing or in their last month: " + ", ".join(stale))

    with open(args.log, "a", encoding="utf-8") as logf:
        proxy.log_line(logf, f"SERVE {set_dir.name}@{proxy.manifest_hash(manifest_path)}")
        proxy.serve(args.port, ca_dir, proxy.known_hosts(manifest), logf,
                    functools.partial(respond, manifest, set_dir))
    return 0


if __name__ == "__main__":  # pragma: no cover -- never reached by an import
    sys.exit(main())
