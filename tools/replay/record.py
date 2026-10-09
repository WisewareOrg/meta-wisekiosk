#!/usr/bin/env python3
"""Records a replay set: forwards every request to its real host and captures the first
response per key. A hand procedure, pipeline timer off; never invoked by run.sh. The only file
under tools/replay/ that dials a real host.

    tools/replay/record.py --set <dir> --port <n> --ca <dir> --expires YYYY-MM-DD
"""
import functools
import hashlib
import http.client
import json
import ssl
import sys
import threading
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

import proxy

_manifest_lock = threading.Lock()


def forward(host, port, method, target, headers, body):  # pragma: no cover -- dials a real host; proven by the host-only proof, not pytest
    """The real upstream's own response to one request, dialled fresh every time, verified
    against the system's default trust store."""
    conn = http.client.HTTPSConnection(host, port, context=ssl.create_default_context(), timeout=30)
    try:
        forward_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ("host", "connection", "proxy-connection", "accept-encoding")
        }
        conn.request(method, target, body=body or None, headers=forward_headers)
        response = conn.getresponse()
        response_body = response.read()
        lines = [f"HTTP/1.1 {response.status} {response.reason}".encode("iso-8859-1")]
        for k, v in response.getheaders():
            if k.lower() in ("connection", "transfer-encoding", "content-length"):
                continue
            lines.append(f"{k}: {v}".encode("iso-8859-1"))
        lines.append(f"Content-Length: {len(response_body)}".encode("iso-8859-1"))
        return b"\r\n".join(lines) + b"\r\n\r\n" + response_body
    finally:
        conn.close()


def respond(manifest, set_dir, method, host, port, target, headers, body, wfile, logf):  # pragma: no cover -- calls forward(), same reason
    """Forwards one request, relays the real response verbatim, and -- only the first time
    this exact key is seen -- writes it and adds the manifest entry, persisted immediately."""
    key = proxy.match_key(method, host, target)
    raw = forward(host, port, method, target, headers, body)
    wfile.write(raw)
    wfile.flush()
    with _manifest_lock:
        if key in manifest.get("responses", {}):
            proxy.log_line(logf, f"FORWARD {key} (already recorded)")
            return
        name = hashlib.sha256(key.encode()).hexdigest()[:16] + ".http"
        responses_dir = set_dir / "responses"
        responses_dir.mkdir(parents=True, exist_ok=True)
        (responses_dir / name).write_bytes(raw)
        manifest.setdefault("responses", {})[key] = {"file": name, "sha256": hashlib.sha256(raw).hexdigest()}
        (set_dir / proxy.MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    proxy.log_line(logf, f"RECORD {key} -> {name}")


def main():  # pragma: no cover -- CLI wiring over respond()/proxy.serve()
    parser = ArgumentParser(description=__doc__, formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument("--set", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--expires", required=True, help="ISO date, the last date in the recorded schedule")
    args = parser.parse_args(sys.argv[1:])

    set_dir = Path(args.set)
    ca_dir = Path(args.ca)
    manifest_path = set_dir / proxy.MANIFEST_NAME
    if manifest_path.is_file():
        manifest = proxy.load_manifest(manifest_path)
    else:
        set_dir.mkdir(parents=True, exist_ok=True)
        manifest = {"expires": args.expires, "responses": {}}
    manifest["expires"] = args.expires

    proxy.serve(args.port, ca_dir, None, sys.stderr, functools.partial(respond, manifest, set_dir))
    return 0


if __name__ == "__main__":  # pragma: no cover -- never reached by an import
    sys.exit(main())
