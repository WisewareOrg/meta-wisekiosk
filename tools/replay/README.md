# tools/replay

The owner of every replay fact: the CA, the proxy/recorder, the manifest shape, and the set
layout. `docs/testing.md` §"Running it" cites this file rather than restating it.

## What this is for

`wisekiosk-backend`'s own outbound calls to upstream weather/park-wait-time data are not
reproducible: a live job's page state depends on what those sources answer at the moment it runs.
A **replay set** is a one-time recording of those calls, committed under `sets/<name>/`; the
**proxy** (`proxy.py replay`) serves it back byte for byte on every later job, with no code path
that ever dials a real host. The **recorder** (`proxy.py record`) is the opposite and separate
entry point that makes the recording — a hand procedure, pipeline timer off, never invoked by
`run.sh`.

## The CA

`ca.sh <dir> ca` mints a 10-year ECDSA P-256 CA under `<dir>` (gitignored `local/keys/replay-ca`
by convention); `ca.sh <dir> leaf <host>` mints a 1-year leaf for `<host>`, signed by that CA, with
`<host>` as the leaf's SAN (Go's own TLS client verifies SAN, never CN). Both refuse to overwrite
existing key material, like `tools/rauc-keygen.sh`; rotation is a fresh directory. Only the CA's
own certificate (`ca.crt`) ever reaches bench, installed by `pipeline-accept-bench-config` at
`/data/config/replay-ca/ca.crt`, mode 0644 so `wisekiosk`'s `User=kiosk` can read it; the CA's own
key and every leaf's key stay on the pipeline host.

## Serving and recording

```sh
tools/replay/proxy.py replay --set sets/<name> --port <n> --ca local/keys/replay-ca [--log <file>]
tools/replay/proxy.py record --set sets/<name> --port <n> --ca local/keys/replay-ca
```

Both terminate TLS themselves (a CONNECT-then-server-handshake proxy), presenting whichever leaf
the CONNECT's own host names. `replay` refuses to start if the set is past its own `expires` date,
or any host it names has no leaf or one expiring within 30 days. A request outside the set
(unknown host, or a method+host+target the manifest never recorded) gets a 502, logged `MISS
<key>`; a served hit is logged `HIT <key> sha256=<hash>`. `record` forwards every request to its
real host over a verified TLS connection and writes the **first** response per key only — a repeat
request still forwards and relays, never overwritten.

## The set layout

```
sets/<name>/
  config.json       -- public coordinates/parks only; installed to bench's /data for the window
  manifest.json      {"expires": "YYYY-MM-DD",
                       "responses": {"<method> <host> <path?query>": {"file": ..., "sha256": ...}}}
  responses/*.http   -- one file per response: the full HTTP/1.1 message (status line, headers,
                        blank line, body), written back byte for byte, nothing recomputed
```

Each entry's `sha256` is that response file's own hash, checked before every replay; a mismatch is
a miss, same as an absent file. The run record's own `<manifest-hash>` token (`replay=<name>@<hash>`)
is a separate, outer hash: `sha256sum manifest.json` — it names which exact recording a job served,
distinct from any one response's integrity hash.

## Re-recording

A set past its `expires` date refuses to serve at all ("replay set expired: re-record"). Point
`wisekiosk.conf` at the recorder (same mechanism `run.sh` uses for `replay`, but with the pipeline
timer off and run by hand — `tools/kiosk-ssh.sh` may hold the tunnel), and reissue every request the
set's own `config.json` implies until each has one recorded response.
