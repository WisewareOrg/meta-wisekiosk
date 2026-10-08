import time
from pathlib import Path

from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS

from .verdict import read_sample, verdict as recovery_verdict

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


class KioskRecoveryTest(WiseKioskCase):

    # Grouped with backend_unreachable for test-report ordering; the
    # stimulus below is self-sufficient (it stops the backend itself) --
    # every case restores its own stimulus in its own cleanup (ruling 5),
    # so this case cannot rely on backend_unreachable's state surviving
    # past that case's own tearDown.
    OETestDepends = [
        "kiosk_backend_unreachable.case.KioskBackendUnreachableTest.test_backend_unreachable"]

    def test_recovery(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(f"test_recovery requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self.target.run, "systemctl start wisekiosk.service")
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")

        mkdir_status, _ = self.target.run(
            "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if mkdir_status != 0:
            raise RuntimeError("could not arm the probe (mkdir)")
        self.target.copyTo(str(_PROBE_SRC), "/home/root/.surf/script.js")

        stop_status, _ = self.target.run("systemctl stop wisekiosk.service")
        if stop_status != 0:
            raise RuntimeError("could not stop wisekiosk.service")
        restart_status, _ = self.target.run("systemctl restart kiosk.service")
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service to arm the probe")

        _status, output = self.target.run(
            _WINDOW_TITLES_PROBE, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        before = read_sample(output)
        if before is None or before["unreachable"] != 1:
            raise RuntimeError("stopping the backend did not reach the unreachable state")

        start_status, _ = self.target.run("systemctl start wisekiosk.service")
        if start_status != 0:
            raise RuntimeError("could not start wisekiosk.service")

        deadline = time.time() + _DEADLINE_SECONDS
        outcome, reason, after = "error", "no probe payload", None
        while True:
            _status, output = self.target.run(
                _WINDOW_TITLES_PROBE, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
            after = read_sample(output)
            outcome, reason = recovery_verdict(before, after)
            if outcome == "ok":
                return
            if time.time() >= deadline:
                break
            time.sleep(_POLL_SECONDS)

        self.fail(f"within {_DEADLINE_SECONDS}s of starting the backend: {reason}")
