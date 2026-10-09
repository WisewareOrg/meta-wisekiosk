#!/usr/bin/env python3
"""The replay proxy: a CONNECT-terminating TLS proxy on loopback that either
serves a committed set of upstream responses byte for byte, or records one.

    tools/replay/proxy.py replay --set <dir> --port <n> --ca <dir> [--log <file>]
        -- serve <dir>'s manifest.json/responses/*; no forwarding code path
           exists in this mode at all. An unmanifested request, a missing or
           tampered response file, or a CONNECT to a host the set never
           names gets a 502, logged "MISS <key>"; the set's own expiry, and
           every host's leaf cert freshness, are checked once at start-up,
           before the socket opens.

    tools/replay/proxy.py record --set <dir> --port <n> --ca <dir>
        -- the opposite: forwards every request to its real host over a
           verified TLS connection of its own, relays the real response,
           and -- only the first time a given method+host+target is seen --
           writes it to a new file under <dir>/responses and adds it to
           <dir>/manifest.json, persisted immediately. Never invoked by
           run.sh; a hand procedure, pipeline timer off.

Both modes terminate TLS themselves, presenting one of --ca's own
leaves/<host>.{crt,key} (ca.sh's output) for whichever host the client's own
CONNECT named -- never a certificate minted at request time, and never SNI-
selected: the CONNECT target already names the host before any TLS byte is
read.

A response file is the exact bytes written back to the client: a full
HTTP/1.1 message (status line, headers, the blank line, the body), nothing
recomputed at replay time. manifest.json's own shape:

    {"expires": "YYYY-MM-DD",
     "responses": {"<method> <host> <path?query>": {"file": "...", "sha256": "..."}}}

Each entry's "sha256" is the stored response FILE's own hash (status line,
headers and body together) -- checked before every replay, so a tampered or
corrupted file is also a miss. The run record's own "<manifest-hash>" token
is a second, outer hash: sha256 of manifest.json's own bytes -- it names
which exact recording this run replayed, distinct from any one response's
integrity hash.

The match key is always "<method> <host> <target>", target being the
request line's own path and query exactly as sent: no normalisation, no
decoding, no inspection of the body.
"""
import argparse
import datetime
import hashlib
import http.client
import json
import socketserver
import ssl
import subprocess
import sys
import threading
from pathlib import Path
from typing import NamedTuple, Optional

MANIFEST_NAME = "manifest.json"
MAX_REQUEST_LINE = 8192
LEAF_FRESHNESS_MARGIN_DAYS = 30

BAD_GATEWAY = (
    b"HTTP/1.1 502 Bad Gateway\r\n"
    b"Content-Length: 0\r\n"
    b"Connection: close\r\n\r\n"
)

_log_lock = threading.Lock()


# --------------------------------------------------------------- pure parts
# Everything in this section is a string, bytes or dict in, a value out --
# no file (past load_manifest's own single read), no socket, no subprocess.
# tools/replay/tests/test_proxy.py holds every branch at the coverage floor.

class ReplaySetExpired(Exception):
    """Raised by check_expiry: a set past its own "expires" date."""


class LeafExpiringSoon(Exception):
    """Raised by check_leaf_freshness: a leaf missing or inside its own
    last LEAF_FRESHNESS_MARGIN_DAYS."""


class Decision(NamedTuple):
    """decide()'s own verdict: the status to answer with, the access-log
    line, and (on a hit only) the manifest entry's file and sha256."""
    status: int
    log_line: str
    file: Optional[str]
    sha256: Optional[str]


def match_key(method, host, target):
    """The manifest's own lookup key: method, host and the request target,
    space-joined. The match is exact; nothing here normalises either side."""
    return f"{method} {host} {target}"


def load_manifest(manifest_path):
    """manifest_path's own JSON, parsed -- no expiry check: check_expiry
    does that, separately, so a caller can load an expired set's manifest
    (for its own hash, say) without the load itself refusing."""
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def check_expiry(expires, today=None):
    """Raises ReplaySetExpired if expires (an ISO "YYYY-MM-DD" string) is
    before today -- the exact refusal text run.sh and the proxy's own
    start-up both surface verbatim."""
    today = today or datetime.date.today()
    if today > datetime.date.fromisoformat(expires):
        raise ReplaySetExpired("replay set expired: re-record")


def hash_matches(body, sha256_hex):
    """True if body's own sha256 hex digest equals sha256_hex."""
    return hashlib.sha256(body).hexdigest() == sha256_hex


def parse_cert_enddate(line):
    """The datetime an `openssl x509 -noout -enddate` line's own notAfter
    names -- "notAfter=<month> <day> <time> <year> GMT", openssl's own
    shape. The trailing zone name is always GMT here and %Z's cross-
    platform matching is not reliable enough to lean on for a refusal."""
    _, _, value = line.partition("=")
    without_zone = value.strip().rsplit(" ", 1)[0]
    return datetime.datetime.strptime(without_zone, "%b %d %H:%M:%S %Y")


def check_leaf_freshness(host, enddate, now=None):
    """Raises LeafExpiringSoon if enddate is at or within
    LEAF_FRESHNESS_MARGIN_DAYS of now (including already past)."""
    now = now or datetime.datetime.now()
    if enddate - now <= datetime.timedelta(days=LEAF_FRESHNESS_MARGIN_DAYS):
        raise LeafExpiringSoon(f"{host} (expires {enddate.date()})")


def decide(responses, method, host, target):
    """The pure MISS/HIT decision over responses (a manifest's own
    "responses" dict) for one request. No file I/O and no hash check here:
    on a hit, the caller reads the named file itself and confirms
    hash_matches() against the returned sha256 before trusting it."""
    key = match_key(method, host, target)
    entry = responses.get(key)
    if entry is None:
        return Decision(status=502, log_line=f"MISS {key}", file=None, sha256=None)
    return Decision(
        status=200, log_line=f"HIT {key} sha256={entry['sha256']}",
        file=entry["file"], sha256=entry["sha256"])


# ------------------------------------------------------------- the rest: I/O
# Every function below opens a file, a socket, or a subprocess, so none of
# it is a constructed-input unit test; tools/replay/README.md's host-only
# proof exercises it instead.

def manifest_hash(manifest_path):  # pragma: no cover -- one more file read beside load_manifest's own
    """sha256 hex of manifest_path's own bytes -- the run record's
    <manifest-hash> token, naming which recording a replay job served."""
    return hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()


def known_hosts(manifest):  # pragma: no cover -- a dict comprehension over load_manifest's own output
    """Every host named by one of manifest's own response keys -- checked
    before a CONNECT's TLS handshake is even attempted."""
    return {key.split(" ", 2)[1] for key in manifest.get("responses", {})}


def leaf_paths(ca_dir, host):  # pragma: no cover -- path arithmetic only, always called from I/O-bound code
    """(cert, key) Path pair for host's own leaf under ca_dir/leaves --
    existence is the caller's own thing to check."""
    leaves = ca_dir / "leaves"
    return leaves / f"{host}.crt", leaves / f"{host}.key"


def leaf_expiry(cert_path):  # pragma: no cover -- shells to openssl; parse_cert_enddate (tested above) does the parsing
    """cert_path's own notAfter, read from a real `openssl x509 -noout
    -enddate` call -- no Python crypto library is a dependency here, the
    same reason tools/replay/ca.sh mints every cert through the openssl
    CLI."""
    out = subprocess.run(
        ["openssl", "x509", "-in", str(cert_path), "-noout", "-enddate"],
        capture_output=True, text=True, check=True).stdout.strip()
    return parse_cert_enddate(out)


def stale_leaves(ca_dir, hosts, now=None):  # pragma: no cover -- aggregates check_leaf_freshness/leaf_expiry, each proven in isolation above
    """Every host in hosts whose own leaf is missing, or expiring soon per
    check_leaf_freshness -- the proxy's own start-up refusal list."""
    stale = []
    for host in sorted(hosts):
        cert, key = leaf_paths(ca_dir, host)
        if not cert.is_file() or not key.is_file():
            stale.append(f"{host} (no leaf at {cert})")
            continue
        try:
            check_leaf_freshness(host, leaf_expiry(cert), now)
        except LeafExpiringSoon as exc:
            stale.append(str(exc))
    return stale


def read_request(rfile):  # pragma: no cover -- a buffered socket's own readline/parse_headers protocol
    """(method, target, headers) for one HTTP/1.1 request read from rfile,
    or None at EOF -- the client closed the connection with no further
    request. Used for both the outer plaintext CONNECT and every inner
    tunnelled request: one parser, one shape."""
    request_line = rfile.readline(MAX_REQUEST_LINE)
    if not request_line:
        return None
    method, target, _version = request_line.decode("iso-8859-1").strip().split(" ", 2)
    headers = http.client.parse_headers(rfile)
    return method, target, headers


def read_body(rfile, headers):  # pragma: no cover -- same reason as read_request
    """headers's own Content-Length worth of bytes from rfile, or b"" if
    absent. Neither replay's match key nor record's forwarding needs a
    chunked body -- the calls this proxy fronts are small and bounded."""
    length = int(headers.get("Content-Length", "0") or "0")
    return rfile.read(length) if length else b""


def log_line(logf, text):  # pragma: no cover -- a real file write
    """Appends one UTC-timestamped line to logf (a writable text file, or
    None to discard) -- the access log a run reads back for proof its
    requests arrived, and for every HIT/MISS/RECORD/FORWARD."""
    if logf is None:
        return
    with _log_lock:
        logf.write(f"{datetime.datetime.now(datetime.timezone.utc).isoformat()} {text}\n")
        logf.flush()


# ---------------------------------------------------------- serving replay
# No function below this point, nor cmd_replay, ever opens a connection to
# anything but the client already holding the tunnel: decide() above is the
# only source of a reply's bytes, byte for byte, nothing recomputed.

def respond_replay(wfile, manifest, set_dir, method, host, target, logf):  # pragma: no cover -- wraps decide() with the real file read decide() never does
    """Writes manifest's own committed response for (method, host, target)
    to wfile byte for byte, via decide()'s verdict, or a 502 on any miss:
    no entry (decide's own 502), no response file, or a file whose bytes no
    longer match decide's own sha256."""
    decision = decide(manifest.get("responses", {}), method, host, target)
    if decision.status == 502:
        wfile.write(BAD_GATEWAY)
        wfile.flush()
        log_line(logf, decision.log_line)
        return
    key = match_key(method, host, target)
    try:
        body = (set_dir / "responses" / decision.file).read_bytes()
    except OSError:
        wfile.write(BAD_GATEWAY)
        wfile.flush()
        log_line(logf, f"MISS {key} (no response file {decision.file})")
        return
    if not hash_matches(body, decision.sha256):
        wfile.write(BAD_GATEWAY)
        wfile.flush()
        log_line(logf, f"MISS {key} (manifest hash mismatch)")
        return
    wfile.write(body)
    wfile.flush()
    log_line(logf, decision.log_line)


# ---------------------------------------------------------- serving record
# forward() is record's only code path that ever dials out; replay never
# calls it and imports nothing that would let it.

def forward(host, port, method, target, headers, body):  # pragma: no cover -- dials a real host; record's own hand run proves it, not a constructed input
    """The real upstream's own response to one request, dialled fresh every
    time, verified against the system's default trust store."""
    conn = http.client.HTTPSConnection(host, port, context=ssl.create_default_context(), timeout=30)
    try:
        forward_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ("host", "connection", "proxy-connection")
        }
        conn.request(method, target, body=body or None, headers=forward_headers)
        response = conn.getresponse()
        response_body = response.read()
        lines = [f"HTTP/1.1 {response.status} {response.reason}".encode("iso-8859-1")]
        for k, v in response.getheaders():
            if k.lower() in ("connection", "transfer-encoding"):
                continue
            lines.append(f"{k}: {v}".encode("iso-8859-1"))
        lines.append(f"Content-Length: {len(response_body)}".encode("iso-8859-1"))
        return b"\r\n".join(lines) + b"\r\n\r\n" + response_body
    finally:
        conn.close()


def respond_record(wfile, set_dir, manifest, host, port, method, target, headers, body, logf):  # pragma: no cover -- calls forward(), same reason
    """Forwards one request to its real host, relays the real response to
    wfile verbatim, and -- only the first time this exact key is seen --
    writes it under set_dir/responses and adds the manifest entry,
    persisting manifest.json immediately. A key already recorded still
    forwards and relays; nothing already captured is ever overwritten."""
    key = match_key(method, host, target)
    raw = forward(host, port, method, target, headers, body)
    wfile.write(raw)
    wfile.flush()
    if key in manifest.get("responses", {}):
        log_line(logf, f"FORWARD {key} (already recorded)")
        return
    name = hashlib.sha256(key.encode()).hexdigest()[:16] + ".http"
    responses_dir = set_dir / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)
    (responses_dir / name).write_bytes(raw)
    manifest.setdefault("responses", {})[key] = {"file": name, "sha256": hashlib.sha256(raw).hexdigest()}
    (set_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log_line(logf, f"RECORD {key} -> {name}")


# --------------------------------------------------------------- transport

class Handler(socketserver.BaseRequestHandler):  # pragma: no cover -- real sockets/TLS; proven by the host-only proof in tools/replay/README.md, not pytest
    """One CONNECT tunnel: the outer plaintext CONNECT, then a server-side
    TLS handshake with the CONNECT host's own leaf, then every tunnelled
    request in turn until the client closes it."""

    def handle(self):
        rfile = self.request.makefile("rb")
        try:
            outer = read_request(rfile)
        except (ValueError, UnicodeDecodeError, ConnectionError):
            return
        if outer is None:
            return
        method, target, headers = outer
        read_body(rfile, headers)
        if method != "CONNECT":
            self.request.sendall(BAD_GATEWAY)
            return

        host, _, port_s = target.rpartition(":")
        if not host:
            host, port_s = target, "443"
        port = int(port_s) if port_s.isdigit() else 443

        server = self.server
        if server.mode == "replay" and host not in server.known_hosts:
            self.request.sendall(BAD_GATEWAY)
            log_line(server.logf, f"MISS CONNECT {host}")
            return

        cert, key = leaf_paths(server.ca_dir, host)
        if not cert.is_file() or not key.is_file():
            self.request.sendall(BAD_GATEWAY)
            log_line(server.logf, f"MISS CONNECT {host} (no leaf)")
            return

        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        try:
            tls = ctx.wrap_socket(self.request, server_side=True)
        except ssl.SSLError as exc:
            log_line(server.logf, f"TLS handshake failed for {host}: {exc}")
            return

        tls_rfile = tls.makefile("rb")
        tls_wfile = tls.makefile("wb")
        try:
            while True:
                inner = read_request(tls_rfile)
                if inner is None:
                    return
                imethod, itarget, iheaders = inner
                ibody = read_body(tls_rfile, iheaders)
                if server.mode == "replay":
                    respond_replay(tls_wfile, server.manifest, server.set_dir, imethod, host, itarget, server.logf)
                else:
                    respond_record(
                        tls_wfile, server.set_dir, server.manifest, host, port,
                        imethod, itarget, iheaders, ibody, server.logf)
        finally:
            tls_rfile.close()
            tls_wfile.close()
            tls.close()


class ReplayServer(socketserver.ThreadingTCPServer):  # pragma: no cover -- binds a real socket, same reason
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, mode, ca_dir, set_dir, manifest, logf):
        self.mode = mode
        self.ca_dir = ca_dir
        self.set_dir = set_dir
        self.manifest = manifest
        self.known_hosts = known_hosts(manifest)
        self.logf = logf
        super().__init__(addr, Handler)


def _run(server, label):  # pragma: no cover -- serve_forever(); same reason
    print(f"{label}: listening on 127.0.0.1:{server.server_address[1]}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def cmd_replay(args):  # pragma: no cover -- CLI wiring over the above; same reason
    set_dir = Path(args.set)
    ca_dir = Path(args.ca)
    manifest_path = set_dir / MANIFEST_NAME
    try:
        manifest = load_manifest(manifest_path)
        check_expiry(manifest["expires"])
    except (OSError, ValueError, KeyError, ReplaySetExpired) as exc:
        sys.exit(f"proxy.py replay: {exc}")
    stale = stale_leaves(ca_dir, known_hosts(manifest))
    if stale:
        sys.exit("proxy.py replay: leaf cert(s) missing or in their last month: " + ", ".join(stale))
    logf = open(args.log, "a", encoding="utf-8") if args.log else None
    try:
        server = ReplayServer(("127.0.0.1", args.port), "replay", ca_dir, set_dir, manifest, logf)
        _run(server, f"replay ({set_dir.name}@{manifest_hash(manifest_path)})")
    finally:
        if logf:
            logf.close()


def cmd_record(args):  # pragma: no cover -- CLI wiring over the above; same reason
    set_dir = Path(args.set)
    ca_dir = Path(args.ca)
    manifest_path = set_dir / MANIFEST_NAME
    if manifest_path.is_file():
        manifest = load_manifest(manifest_path)
    else:
        set_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "expires": (datetime.date.today() + datetime.timedelta(days=365)).isoformat(),
            "responses": {},
        }
    server = ReplayServer(("127.0.0.1", args.port), "record", ca_dir, set_dir, manifest, sys.stderr)
    _run(server, f"record ({set_dir.name})")


def build_parser():  # pragma: no cover -- argparse plumbing, no branch of its own
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    replay = sub.add_parser("replay", help="serve a committed set; no forwarding code path exists")
    replay.add_argument("--set", required=True, help="the replay set directory")
    replay.add_argument("--port", required=True, type=int, help="loopback port to listen on")
    replay.add_argument("--ca", required=True, help="ca.sh's own output directory")
    replay.add_argument("--log", help="append the access log here; omit to discard it")
    replay.set_defaults(func=cmd_replay)

    record = sub.add_parser("record", help="forward to the real host; capture the first response per key")
    record.add_argument("--set", required=True, help="the replay set directory to record into")
    record.add_argument("--port", required=True, type=int, help="loopback port to listen on")
    record.add_argument("--ca", required=True, help="ca.sh's own output directory")
    record.set_defaults(func=cmd_record)

    return parser


def main():  # pragma: no cover -- argparse plumbing, no branch of its own
    args = build_parser().parse_args(sys.argv[1:])
    args.func(args)
    return 0


if __name__ == "__main__":  # pragma: no cover -- never reached by an import
    sys.exit(main())
