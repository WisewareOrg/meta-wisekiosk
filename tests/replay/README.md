# Replay sets

A replay set is three files under `tests/replay/sets/<name>/`, read by a target-suite test that
parametrizes [WiseBenchManager](https://github.com/WisewareOrg/WiseBenchManager)'s `proxy` fixture
(its README, "Running it") with the set's HAR:

```
sets/<name>/
  config.json   -- the kiosk config this set is recorded against: public coordinates and park
                   IDs only, installed to the appliance's /data for the window the set covers
  expected.json -- the page state the set's recorded traffic fills the page to, once a test has
                   fetched it through the replayed proxy (below)
  flows.har     -- the recorded network traffic itself, in mitmproxy's own HAR dump format
                   (`hardump`): every request/response pair the appliance issued when `config.json`
                   was live, byte for byte
```

`flows.har` is read by `mitmdump --server-replay <har> --set server_replay_extra=kill ...` (the
`proxy` fixture's own invocation): a request matching one of the HAR's recorded `method host
path?query` keys gets that recording's response; any other request is killed and ends the test
session, so a set only serves traffic it actually recorded. No manifest or per-response file exists
alongside it — the HAR is the one artifact, matched and replayed by mitmdump itself.

A set carries no expiry. What a recording keeps or drops is decided once, at recording time, by
whoever records it — not refreshed on a schedule and not something a tool recomputes later.

## `cards4-live`

Recorded against `config.json`'s four `themeparks.wiki` park IDs and its `open-meteo.com` weather
location: one weather forecast call, and one `/live` plus one `/schedule` call per park — nine
requests in total, matching the nine entries in `flows.har`.

`expected.json`'s `cards` field is `<present>/<live>` in the page probe's own units: `present` is
the number of parks `config.json` names, and `live` is how many of those parks' recorded `/live`
responses carry at least one entity whose `status` is `OPERATING` with a posted `queue.STANDBY`
wait time. `faulted` and `unreachable` are `0` because every recorded request succeeded with a
`200` response the appliance's modules can parse.

## Re-recording a set by hand

There is no recording command in the runner or this layer — mitmproxy's own `mitmdump` is the
whole tool, pointed at a scratch HAR path:

```sh
mitmdump --listen-host 127.0.0.1 --listen-port <port> --set hardump=<path>.har
```

mitmproxy writes its CA to `~/.mitmproxy/mitmproxy-ca-cert.pem` on first start. With `mitmdump`
listening, fetch every URL the set should hold, verbatim, through it as an HTTP(S) proxy — `curl
-sS --proxy http://127.0.0.1:<port> --cacert ~/.mitmproxy/mitmproxy-ca-cert.pem <url>` once per URL
for `cards4-live`'s nine, one weather call and a live/schedule pair per park named in
`config.json`. mitmproxy matches a replayed request on method, host, path and query, so a
re-recording's URLs must stay byte-identical to the ones the appliance actually sends.

Stop `mitmdump` cleanly (`SIGINT`) once every URL has been fetched — the HAR is only written out on
a clean exit. Before committing: `jq '.log.entries | length' <path>.har` must equal the number of
URLs fetched, and the recording must still clear [`CONTRIBUTING.md`](../../CONTRIBUTING.md)'s
public-repository rule — read it before assuming a third-party API's own response headers do.
