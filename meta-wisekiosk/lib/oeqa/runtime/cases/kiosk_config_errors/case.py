import re
import time
from pathlib import Path

from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS

from .verdict import parse_configuration_error

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
_DEADLINE_SECONDS = 90
_POLL_SECONDS = 2


class KioskConfigErrorsTest(WiseKioskCase):

    def test_configuration_errors(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_configuration_errors requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")

        mkdir_status, _ = self.target.run(
            "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if mkdir_status != 0:
            raise RuntimeError("could not arm the probe (mkdir)")
        self.target.copyTo(str(_PROBE_SRC), "/home/root/.surf/script.js")
        deadline = time.time() + _DEADLINE_SECONDS
        restart_status, _ = self.target.run(
            "systemctl restart kiosk.service", timeout=int(max(1, deadline - time.time())))
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service to arm the probe")

        state = "no-probe"
        while True:
            _status, output = self.target.run(
                _WINDOW_TITLES_PROBE, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
            for line in output.splitlines():
                m = _WM_NAME.match(line)
                if not m:
                    continue
                found = parse_configuration_error(m.group(1))
                if found is not None:
                    state = found
                    break
                if "WK1 " in m.group(1):
                    state = "absent-field"
            if state == "absent-field":
                return
            if time.time() >= deadline:
                break
            time.sleep(_POLL_SECONDS)

        self.fail(
            f"a configuration-error={state!r} is still present {_DEADLINE_SECONDS}s after the "
            "restart -- the healthy config.json on this board was not read as applied")
