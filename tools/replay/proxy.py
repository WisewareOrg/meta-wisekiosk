"""The CONNECT/TLS acceptor `replay.py` and `record.py` both build on, plus the pure manifest/CA
parts both share. `tools/replay/README.md` owns the format, hash, CA and no-connection facts this
module's functions implement.
"""
import datetime
import hashlib
import http.client
import json
import socketserver
import ssl
import subprocess
import threading
from pathlib import Path

MANIFEST_NAME = "manifest.json"
MAX_REQUEST_LINE = 8192
LEAF_FRESHNESS_MARGIN_DAYS = 30

BAD_GATEWAY = (
    b"HTTP/1.1 502 Bad Gateway\r\n"
    b"Content-Length: 0\r\n"
    b"Connection: close\r\n\r\n"
)

_log_lock = threading.Lock()


def match_key(method, host, target):
    return f"{method} {host} {target}"


def load_manifest(manifest_path):
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def hash_matches(body, sha256_hex):
    return hashlib.sha256(body).hexdigest() == sha256_hex


def parse_cert_enddate(line):
    """The datetime an `openssl x509 -noout -enddate` line's own notAfter names."""
    _, _, value = line.partition("=")
    without_zone = value.strip().rsplit(" ", 1)[0]
    return datetime.datetime.strptime(without_zone, "%b %d %H:%M:%S %Y")


def check_leaf_freshness(host, enddate, now=None):
    """A reason string if enddate is at or within LEAF_FRESHNESS_MARGIN_DAYS of now, else None."""
    now = now or datetime.datetime.now()
    if enddate - now <= datetime.timedelta(days=LEAF_FRESHNESS_MARGIN_DAYS):
        return f"{host} (expires {enddate.date()})"
    return None


def decide(responses, method, host, target):
    """responses's own entry ({"file", "sha256"}) for (method, host, target), or None on a miss."""
    return responses.get(match_key(method, host, target))


def known_hosts(manifest):
    """Every host named by one of manifest's own response keys."""
    return {key.split(" ", 2)[1] for key in manifest.get("responses", {})}


def leaf_paths(ca_dir, host):
    leaves = ca_dir / "leaves"
    return leaves / f"{host}.crt", leaves / f"{host}.key"


def manifest_hash(manifest_path):
    return hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()


def read_request(rfile):
    """(method, target, headers) for one HTTP/1.1 request read from rfile, or None at EOF."""
    request_line = rfile.readline(MAX_REQUEST_LINE)
    if not request_line:
        return None
    method, target, _version = request_line.decode("iso-8859-1").strip().split(" ", 2)
    headers = http.client.parse_headers(rfile)
    return method, target, headers


def read_body(rfile, headers):
    """headers's own Content-Length worth of bytes from rfile, or b"" if absent."""
    length = int(headers.get("Content-Length", "0") or "0")
    return rfile.read(length) if length else b""


def log_line(logf, text):
    """Appends one UTC-timestamped line to logf."""
    with _log_lock:
        logf.write(f"{datetime.datetime.now(datetime.timezone.utc).isoformat()} {text}\n")
        logf.flush()


def leaf_expiry(cert_path):  # pragma: no cover -- shells to openssl; parse_cert_enddate does the parsing
    """cert_path's own notAfter, from a real `openssl x509 -noout -enddate` call."""
    out = subprocess.run(
        ["openssl", "x509", "-in", str(cert_path), "-noout", "-enddate"],
        capture_output=True, text=True, check=True).stdout.strip()
    return parse_cert_enddate(out)


def stale_leaves(ca_dir, hosts, now=None):  # pragma: no cover -- aggregates leaf_expiry (I/O); check_leaf_freshness proven above
    """Every host in hosts whose own leaf is missing or expiring soon."""
    stale = []
    for host in sorted(hosts):
        cert, key = leaf_paths(ca_dir, host)
        if not cert.is_file() or not key.is_file():
            stale.append(f"{host} (no leaf at {cert})")
            continue
        reason = check_leaf_freshness(host, leaf_expiry(cert), now)
        if reason:
            stale.append(reason)
    return stale


class Handler(socketserver.BaseRequestHandler):  # pragma: no cover
    """One CONNECT tunnel: the plaintext CONNECT, a server-side TLS handshake with the CONNECT
    host's own leaf, then every tunnelled request through server.responder in turn."""

    def handle(self):
        server = self.server
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
            log_line(server.logf, f"MISS {method} {target} (not a CONNECT)")
            return

        host, _, port_s = target.rpartition(":")
        if not host:
            host, port_s = target, "443"
        port = int(port_s) if port_s.isdigit() else 443

        if server.known_hosts is not None and host not in server.known_hosts:
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
            log_line(server.logf, f"MISS {host} (TLS handshake failed: {exc})")
            return

        tls_rfile = tls.makefile("rb")
        tls_wfile = tls.makefile("wb")
        try:
            while True:
                try:
                    inner = read_request(tls_rfile)
                except (ValueError, UnicodeDecodeError, ConnectionError) as exc:
                    log_line(server.logf, f"MISS {host} (malformed request: {exc})")
                    return
                if inner is None:
                    return
                imethod, itarget, iheaders = inner
                ibody = read_body(tls_rfile, iheaders)
                server.responder(imethod, host, port, itarget, iheaders, ibody, tls_wfile, server.logf)
        finally:
            tls_rfile.close()
            tls_wfile.close()
            tls.close()


class ProxyServer(socketserver.ThreadingTCPServer):  # pragma: no cover -- binds a real socket, same reason
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, port, ca_dir, known_hosts_set, logf, responder):
        self.ca_dir = ca_dir
        self.known_hosts = known_hosts_set
        self.logf = logf
        self.responder = responder
        super().__init__(("127.0.0.1", port), Handler)


def serve(port, ca_dir, known_hosts_set, logf, responder):  # pragma: no cover -- serve_forever(); same reason
    """Runs a CONNECT-terminating TLS proxy on 127.0.0.1:port until interrupted. For every
    tunnelled request, calls responder(method, host, port, target, headers, body, wfile, logf).
    known_hosts_set=None accepts a CONNECT to any host with a leaf; a real set refuses any other."""
    server = ProxyServer(port, ca_dir, known_hosts_set, logf, responder)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
