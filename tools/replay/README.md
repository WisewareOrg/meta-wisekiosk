# tools/replay

The owner of every replay fact: the CA, the proxy, the recorder, the manifest shape, and the set
layout. `docs/testing.md` §"Running it" cites this file rather than restating it.

## What this is for

`wisekiosk-backend`'s own outbound calls to upstream weather/park-wait-time data are not
reproducible: a live job's page state depends on what those sources answer at the moment it runs.
A **replay set** is a one-time recording of those calls, committed under `sets/<name>/`; `replay.py`
serves it back byte for byte on every later job, with no code path that ever dials a real host.
`record.py` is the opposite and separate entry point that makes the recording — a hand procedure,
pipeline timer off, never invoked by `run.sh`. Both build on `proxy.py`, the shared CONNECT/TLS
acceptor; only `record.py` ever opens a connection to anything but the client already holding the
tunnel.

## The CA

`ca.sh <dir> ca` mints a 10-year ECDSA P-256 CA under `<dir>` (gitignored `local/keys/replay-ca` by
convention); `ca.sh <dir> leaf <host>` mints a 1-year leaf for `<host>`, signed by that CA, with
`<host>` as the leaf's SAN (Go's own TLS client verifies SAN, never CN) and `extendedKeyUsage=
serverAuth`. Both refuse to overwrite existing key material, like `tools/rauc-keygen.sh`: the CA
rotates into a fresh directory, a leaf rotates by removing its own files first and re-minting — the
CA itself never needs to change for a leaf renewal. **A leaf needs re-minting yearly**; `replay.py`
refuses to start once any leaf its set names is within 30 days of its own expiry. Only the CA's own
certificate (`ca.crt`) ever reaches bench, installed by `pipeline-accept-bench-config` at
`/data/config/replay-ca/ca.crt`, mode 0644 so `wisekiosk`'s `User=kiosk` can read it; the CA's own
key and every leaf's key stay on the pipeline host.

## Serving and recording

```sh
tools/replay/replay.py --set sets/<name> --port <n> --ca local/keys/replay-ca --log <file>
tools/replay/record.py --set sets/<name> --port <n> --ca local/keys/replay-ca --expires YYYY-MM-DD
```

Both terminate TLS themselves (a CONNECT-then-server-handshake proxy), presenting whichever leaf
the CONNECT's own host names. `replay.py` refuses to start if the set is past its own `expires`
date, or any host it names has no leaf or one expiring within 30 days; its own access log's first
line is `SERVE <name>@<manifest-hash>`, the proxy's own measurement of which recording it is
serving. A request outside the set (an unknown host, or a method+host+target the manifest never
recorded) gets a 502, logged `MISS <key>`; a served hit is logged `HIT <key> sha256=<hash>`.
`record.py` forwards every request to its real host over a verified TLS connection, strips
`Accept-Encoding` so the upstream answers uncompressed (a committed response file must stay text,
for `tools/scrub-identity.py`'s own scan) and drops the upstream's own `Content-Length` in favour of
one computed from the stored body, and writes the **first** response per key only — a repeat
request still forwards and relays, never overwritten. `record.py` refuses a CONNECT to any host
with no leaf (`MISS CONNECT <host> (no leaf)`), the same as `replay.py`.

## The set layout

```
sets/<name>/
  config.json       -- public coordinates/parks only; installed to bench's /data for the window
  manifest.json      {"expires": "YYYY-MM-DD", "expect_cards": "<present>/<live>",
                       "responses": {"<method> <host> <path?query>": {"file": ..., "sha256": ...}}}
  responses/*.http   -- one file per response: the full HTTP/1.1 message (status line, headers,
                        blank line, body), written back byte for byte, nothing recomputed
```

Each entry's `sha256` is that response file's own hash, checked before every replay; a mismatch is
a miss, same as an absent file. `expect_cards` is the one owner of what the applied case's own
`cards=` should read once the set is live (`run.sh` compares it against the run record after
`testimage`); the key must be present, even if empty for a set with no park module such as
`weather-only` — a missing key voids every job. The run record's own `<manifest-hash>` token
(`replay=<name>@<hash>`) is a separate, outer hash — `replay.py`'s own `SERVE` line, sha256 of
`manifest.json`'s bytes — distinct from any one response's integrity hash.

## Re-recording

A set past its `expires` date refuses to serve at all (`replay set expired: re-record`). To
re-record (pipeline timer off throughout):

1. Mint a leaf for every upstream host the set's own `config.json` will call, if none already
   exists or any is within its last month: `tools/replay/ca.sh local/keys/replay-ca leaf <host>`.
   `record.py` refuses a CONNECT to a host with no leaf.
2. Point bench at the recorder: write `/data/config/wisekiosk.conf` by hand with `HTTPS_PROXY=
   http://127.0.0.1:<port>`, `SSL_CERT_FILE=/data/config/replay-ca/ca.crt`, `SSL_CERT_DIR=
   /data/config/replay-ca`, install the set's own `config.json` to `/data/config/config.json`, and
   restart `wisekiosk.service`. `tools/kiosk-ssh.sh` may hold the tunnel for this.
3. On the pipeline host, open the same reverse tunnel `run.sh` uses (`ssh -R
   127.0.0.1:<port>:127.0.0.1:<port>`) and run `tools/replay/record.py --set sets/<name> --port
   <port> --ca local/keys/replay-ca --expires <the last date in the recorded schedule>`.
4. Restart `kiosk.service` so the page issues every request the config implies (one weather call, a
   live and a schedule call per park); watch `record.py`'s own stderr for a `RECORD <key> -> <file>`
   line per request, until every expected key has one.
5. Stop `record.py`, remove bench's `wisekiosk.conf`, restore its own `config.json`, restart
   `wisekiosk.service` then `kiosk.service`, and close the tunnel.
6. Add (or confirm) the set's own `expect_cards` in `manifest.json` by hand — `record.py` never
   writes it. Editing the file this way changes its own bytes, so the run record's own
   `<manifest-hash>` token changes too; that is expected, not a sign the recording failed.
7. Review the new `sets/<name>/` tree before committing: `tools/scrub-identity.py --check` and a
   human read confirm `config.json` names only public, non-site coordinates and parks.
