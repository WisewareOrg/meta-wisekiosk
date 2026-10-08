import re
from pathlib import Path

from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS

from .verdict import parse_layout, verdict as layout_verdict

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

_WM_NAME = re.compile(r'WM_NAME\(\w+\) = "(.*)"$')


class KioskLayoutTest(WiseKioskCase):

    # Grouped with backend_unreachable (the banner this case measures
    # clearance against is raised by the same stimulus, applied below) --
    # every case restores its own stimulus in its own cleanup (ruling 5),
    # so this case stops the backend itself rather than relying on
    # backend_unreachable's state surviving past that case's own tearDown.
    OETestDepends = [
        "kiosk_backend_unreachable.case.KioskBackendUnreachableTest.test_backend_unreachable"]

    def test_layout_floor(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(f"test_layout_floor requires role=bench, got {WiseKioskCase.role!r}")
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
        parsed = None
        for line in output.splitlines():
            m = _WM_NAME.match(line)
            if not m:
                continue
            parsed = parse_layout(m.group(1))
            if parsed is not None:
                break
        if parsed is None:
            raise RuntimeError("no probe payload carried a layout= field")

        outcome, reason = layout_verdict(parsed)
        if outcome != "ok":
            self.fail(reason)
