# Replay sets

A replay set is two files under `tests/replay/sets/<name>/`, read by a target-suite test that
parametrizes [WiseBenchManager](https://github.com/WisewareOrg/WiseBenchManager)'s `proxy` fixture
(its README, "What a layer provides") with the set's HAR:

```
sets/<name>/
  config.json -- the kiosk config this set is recorded against: public coordinates and park
                 IDs only
  flows.har   -- the recorded network traffic itself, in mitmproxy's own HAR dump format
                 (`hardump`): the responses to the URLs the appliance requests under
                 `config.json`, recorded by fetching them through mitmdump
```

A set carries no expiry. What a recording keeps or drops is decided once, at recording time, by
whoever records it — not refreshed on a schedule and not something a tool recomputes later.

## `cards4-live`

Recorded against `config.json`'s four `themeparks.wiki` park IDs and its `open-meteo.com` weather
location: one weather forecast call, and one `/live` plus one `/schedule` call per park.

This set is recorded while all four configured parks are open.

## Re-recording an existing set by hand

There is no recording command in the runner or this layer — mitmproxy's own `mitmdump` is the
whole tool. [WiseBenchManager](https://github.com/WisewareOrg/WiseBenchManager)'s README,
"Running it", gives the `hardump` invocation that points it at a scratch HAR path, and where
mitmproxy writes its CA on first start.

The URLs to record are the ones the instance itself requested in a run of the set's test, served
and killed alike — after an app change, the failing run. That run's flow file,
`proxy-<test>-<n>.flows` beside its `report.jsonl` (WiseBenchManager's README, "The record"),
holds every one of them, and mitmproxy lists them with full URLs:

```sh
mitmdump -nr <run dir>/proxy-<test>-<n>.flows --flow-detail 2
```

Each flow starts with a `<client>: <METHOD> <URL> HTTP/<version>` line; a served one continues
`[replay] << …`, a killed one `<< Connection killed.`. With the recording `mitmdump` listening,
fetch each distinct URL once, verbatim and in the order it first appears, through it as an
HTTP(S) proxy — `curl -sS --proxy http://127.0.0.1:<port> --cacert
~/.mitmproxy/mitmproxy-ca-cert.pem <url>`. mitmproxy matches a replayed request on method, host,
path and query, so the recorded URLs must stay byte-identical to the ones the instance requested.

Stop `mitmdump` cleanly (`SIGINT`) once every URL has been fetched — the HAR is only written out on
a clean exit. Before committing: `jq '.log.entries | length' <path>.har` must equal the number of
distinct URLs fetched, and the recording must still clear [`CONTRIBUTING.md`](../../CONTRIBUTING.md)'s
public-repository rule — read it before assuming a third-party API's own response headers do.

mitmdump's HAR carries each entry's own `serverIPAddress` and, behind Cloudflare, a `cf-ray`
response header whose suffix names the edge location that served the request — a coarse location of
the host doing the recording, not of the appliance. Drop every entry's `serverIPAddress` field and
every response header whose name starts `cf-` (case-insensitive — `cf-ray`, `cf-cache-status`, and
any other Cloudflare header a future recording picks up) before committing, a one-off edit at
recording time, not a kept script:

```sh
jq '.log.entries[] |= (del(.serverIPAddress) |
    .response.headers |= map(select(.name | ascii_downcase | startswith("cf-") | not)))' \
  raw.har > sets/<name>/flows.har
```
