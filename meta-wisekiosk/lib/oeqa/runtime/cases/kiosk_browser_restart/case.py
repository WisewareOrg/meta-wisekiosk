import time
from pathlib import Path

from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS
from kiosk_applied.verdict import read_sample

# The one probe script (design §2.5: "one probe script, one record format"),
# owned by kiosk_applied -- referenced here rather than duplicated.
_PROBE_SRC = Path(__file__).resolve().parents[1] / "kiosk_applied" / "probe.js"

# Walks the root's whole tree and reads every window's WM_NAME -- the same
# probe channel kiosk_applied's case.py arms. docs/testing.md § "The render
# and applied cases" has the why.
_WINDOW_TITLES_PROBE = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | "
    "awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)

_DEADLINE_SECONDS = 60
_POLL_SECONDS = 2


class KioskBrowserRestartTest(WiseKioskCase):

    def test_browser_restart(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_browser_restart requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")

        mkdir_status, _ = self.target.run(
            "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if mkdir_status != 0:
            raise RuntimeError("could not arm the probe (mkdir)")
        self.target.copyTo(str(_PROBE_SRC), "/home/root/.surf/script.js")

        status, _ = self.target.run("pgrep -x surf")
        if status != 0:
            raise RuntimeError("surf is not running before the kill")

        kill_status, _ = self.target.run("kill -TERM $(pgrep -x surf)")
        if kill_status != 0:
            raise RuntimeError("could not send SIGTERM to surf")

        deadline = time.time() + _DEADLINE_SECONDS
        sample = None
        while True:
            _status, output = self.target.run(
                _WINDOW_TITLES_PROBE, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
            sample = read_sample(output)
            if sample and sample["state"] == "applied":
                return
            if time.time() >= deadline:
                break
            time.sleep(_POLL_SECONDS)

        if sample is None:
            self.fail(
                f"no probe payload within {_DEADLINE_SECONDS}s of killing surf -- "
                "kiosk.service did not restart it")
        self.fail(f"page not applied within {_DEADLINE_SECONDS}s of killing surf -- "
                  f"state={sample['state']}")
