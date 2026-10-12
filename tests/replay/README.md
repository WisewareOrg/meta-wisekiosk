# Replay sets

A replay set is three files under `tests/replay/sets/<name>/`, read by a target-suite test that
parametrizes [WiseBenchManager](https://github.com/WisewareOrg/WiseBenchManager)'s `proxy` fixture
(its README, "Running it") with the set's HAR:

```
sets/<name>/
  config.json   -- the kiosk config this set is recorded against: public coordinates and park
                   IDs only
  expected.json -- the page state the set's recorded traffic fills the page to, once a test has
                   fetched it through the replayed proxy (below)
  flows.har     -- the recorded network traffic itself, in mitmproxy's own HAR dump format
                   (`hardump`): the responses to the URLs the appliance requests under
                   `config.json`, recorded by fetching them through mitmdump
```

A set carries no expiry. What a recording keeps or drops is decided once, at recording time, by
whoever records it — not refreshed on a schedule and not something a tool recomputes later.

## `cards4-live`

Recorded against `config.json`'s four `themeparks.wiki` park IDs and its `open-meteo.com` weather
location: one weather forecast call, and one `/live` plus one `/schedule` call per park — nine
requests in total, matching the nine entries in `flows.har`.

`expected.json`'s `cards` field is `<present>/<live>`: `present` is the number of parks
`config.json` names, and `live` is how many of those parks' recorded `/live` responses carry at
least one attraction (`entityType` `ATTRACTION`) whose `status` is `OPERATING` with a posted
`queue.STANDBY` wait time. `faulted` and `unreachable` are `0` because every recorded request
succeeded with a `200` response the appliance's modules can parse.

This set is recorded while all four configured parks are open, so its `expected.json` must derive
to `4/4` — a recording where fewer parks come out live does not represent what the name
`cards4-live` promises and does not belong under it.

## Re-recording an existing set by hand

There is no recording command in the runner or this layer — mitmproxy's own `mitmdump` is the
whole tool, pointed at a scratch HAR path:

```sh
mitmdump --listen-host 127.0.0.1 --listen-port <port> --set hardump=<path>.har
```

mitmproxy writes its CA to `~/.mitmproxy/mitmproxy-ca-cert.pem` on first start. The set's own
committed HAR names the URLs to fetch and the order to fetch them in:

```sh
jq -r '.log.entries[].request.url' sets/<name>/flows.har
```

With `mitmdump` listening, fetch each of those URLs, verbatim and in that order, through it as an
HTTP(S) proxy — `curl -sS --proxy http://127.0.0.1:<port> --cacert
~/.mitmproxy/mitmproxy-ca-cert.pem <url>` once per URL. mitmproxy matches a replayed request on
method, host, path and query, so a re-recording's URLs must stay byte-identical to the ones the
old recording held.

(Capturing a *new* set's URLs — one with no existing HAR to extract them from — means pointing the
appliance itself at the recorder instead of `curl`, which is the replay-mode switch issue #225 (the
target suite's conftest fixtures) builds; out of scope for re-recording an existing set.)

Stop `mitmdump` cleanly (`SIGINT`) once every URL has been fetched — the HAR is only written out on
a clean exit. Before committing: `jq '.log.entries | length' <path>.har` must equal the number of
URLs fetched, and the recording must still clear [`CONTRIBUTING.md`](../../CONTRIBUTING.md)'s
public-repository rule — read it before assuming a third-party API's own response headers do.

mitmdump's HAR carries each entry's own `serverIPAddress` and, behind Cloudflare, a `cf-ray`
response header whose suffix names the edge location that served the request — a coarse location of
the host doing the recording, not of the appliance. Drop every entry's `serverIPAddress` field and
every `cf-ray`/`cf-cache-status` response header before committing (a one-off `jq`/`python` edit at
recording time, not a kept script); mitmproxy's replay match is on method, host, path and query, so
removing response headers changes nothing about what a later replay serves.
