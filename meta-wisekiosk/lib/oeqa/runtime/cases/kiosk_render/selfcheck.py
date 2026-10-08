import time

from framework.base import POLL_ATTEMPT_TIMEOUT_SECONDS, POLL_SECONDS, WiseKioskCase

from .case import RENDER_PROBE
from .verdict import verdict as render_verdict

_PAINT_WAIT_SECONDS = 180
_WEBKIT_PGREP = "pgrep -f '[W]ebKitWebProcess' | head -n 1"


def wait_for_painted(case):
    # A page that is still loading after a kiosk.service restart captures as a
    # uniform region; the two-frame check is meaningful only once it has painted.
    deadline = time.monotonic() + _PAINT_WAIT_SECONDS
    while True:
        _status, output = case.target.run(RENDER_PROBE)
        outcome, reason = render_verdict(output.splitlines())
        if not (outcome == "error" and "uniform" in reason):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"the page did not paint within {_PAINT_WAIT_SECONDS}s: {reason}")
        time.sleep(POLL_SECONDS)


def _is_stopped(case, pid):
    status, stat = case.target.run(f"cat /proc/{pid}/stat")
    if status != 0:
        return False
    fields = stat.split()
    return len(fields) > 2 and fields[2] == "T"


class KioskRenderSelfcheck(WiseKioskCase):

    def test_render_detects_frozen_process(self):
        restart_status, _ = self.target.run(
            "systemctl restart kiosk.service", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service")
        wait_for_painted(self)

        _status, pid = self.target.run(_WEBKIT_PGREP)
        pid = pid.strip()
        if not pid:
            raise RuntimeError("no WebKitWebProcess found on the device")

        def resume_if_stopped():
            if _is_stopped(self, pid):
                cont_status, _ = self.target.run(f"kill -CONT {pid}")
                if cont_status != 0:
                    raise RuntimeError(f"could not CONT WebKitWebProcess (pid={pid})")

        self.addCleanup(resume_if_stopped)

        stop_status, _ = self.target.run(f"kill -STOP {pid}")
        if stop_status != 0:
            raise RuntimeError(f"could not STOP WebKitWebProcess (pid={pid})")

        _status, output = self.target.run(RENDER_PROBE)
        outcome, reason = render_verdict(output.splitlines())
        if outcome != "frozen":
            self.fail(f"STOPping WebKitWebProcess did not read as frozen -- got {outcome!r} ({reason})")

        cont_status, _ = self.target.run(f"kill -CONT {pid}")
        if cont_status != 0:
            raise RuntimeError(f"could not CONT WebKitWebProcess (pid={pid})")
        wait_for_painted(self)

        _status, output = self.target.run(RENDER_PROBE)
        outcome, reason = render_verdict(output.splitlines())
        if outcome != "advancing":
            self.fail(f"did not return to advancing after CONT -- got {outcome!r} ({reason})")
