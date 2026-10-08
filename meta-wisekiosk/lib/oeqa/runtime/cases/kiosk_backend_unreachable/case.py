import time
from pathlib import Path

from kiosk_applied.verdict import read_sample as applied_read_sample
from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS

from .verdict import read_sample, verdict as unreachable_verdict

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

_DEADLINE_SECONDS = 30
_POLL_SECONDS = 2
_APPLIED_WAIT_SECONDS = 180


class KioskBackendUnreachableTest(WiseKioskCase):

    def test_backend_unreachable(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_backend_unreachable requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self.target.run, "systemctl start wisekiosk.service")
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")

        mkdir_status, _ = self.target.run(
            "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if mkdir_status != 0:
            raise RuntimeError("could not arm the probe (mkdir)")
        self.target.copyTo(str(_PROBE_SRC), "/home/root/.surf/script.js")
        restart_status, _ = self.target.run("systemctl restart kiosk.service")
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service to arm the probe")
        # The banner is the running page's reaction; stopping the backend
        # before the page has applied yields a load failure instead.
        applied_by = time.time() + _APPLIED_WAIT_SECONDS
        while True:
            _status, output = self.target.run(
                _WINDOW_TITLES_PROBE, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
            sample = applied_read_sample(output)
            if sample is not None and sample.get("state") == "applied":
                break
            if time.time() >= applied_by:
                last = sample.get("state") if sample else "no probe payload"
                raise RuntimeError(
                    f"the page did not apply within {_APPLIED_WAIT_SECONDS}s of arming the probe (last: {last})")
            time.sleep(_POLL_SECONDS)

        stop_status, _ = self.target.run("systemctl stop wisekiosk.service")
        if stop_status != 0:
            raise RuntimeError("could not stop wisekiosk.service")

        deadline = time.time() + _DEADLINE_SECONDS
        outcome, reason = "error", "no probe payload"
        while True:
            _status, output = self.target.run(
                _WINDOW_TITLES_PROBE, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
            sample = read_sample(output)
            outcome, reason = unreachable_verdict(sample)
            if outcome == "ok":
                return
            if time.time() >= deadline:
                break
            time.sleep(_POLL_SECONDS)

        self.fail(f"within {_DEADLINE_SECONDS}s of stopping the backend: {reason}")
