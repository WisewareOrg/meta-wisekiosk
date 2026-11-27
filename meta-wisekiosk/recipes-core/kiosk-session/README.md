# kiosk-session

`kiosk-session_1.0.bb` builds `files/kiosk-browser.c` against WPE WebKit and libsystemd and installs
`/usr/bin/kiosk-browser` with `kiosk.service`, which is enabled in `multi-user.target`.

`kiosk-browser URL` shows one page fullscreen:

- It waits, petting the watchdog, until vt1 is in front, and exits 0 when another console is
  brought forward.
- A page that fails to load is retried in place every 5 s; the first failure since a page last
  loaded is logged and the error is the service status.
- It pets the watchdog each time the page answers a script evaluation, and exits 1 when the web
  process ends.
- `enable-developer-extras` is on, and WebKit's damage propagation is off so the whole frame
  repaints.

## How it fits

- `kiosk.service` runs after `network-online.target` and `data.mount`, with `WatchdogSec=30` and
  `Restart=always`, backing off from 1 s to 10 s. A page that stops answering is restarted.
- `WPE_PLATFORM=drm` makes an unopenable display abort the browser with the reason.
- The page is the local app served by `wisekiosk.service`; `kiosk-drmgrab` captures what the panel
  scans out.

Part of [the display](../../../docs/display.md).

## Knobs

- `KIOSK_URL`: `http://localhost:8080` in the unit, overridden by `/data/config/kiosk.conf`
  (an optional `EnvironmentFile`).
- `WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:2999` in `kiosk.conf` turns the remote inspector on.
- `WatchdogSec` in `files/kiosk.service`: how long the page may go unanswered before systemd stops
  and restarts the browser.
- `PERIOD` (5 s) in `kiosk-browser.c`: the load retry and watchdog-poll interval.
