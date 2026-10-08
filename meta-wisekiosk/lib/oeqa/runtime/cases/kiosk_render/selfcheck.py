import time

from framework.base import WiseKioskCase

from .case import _RENDER_PROBE, _wait_for_painted
from .verdict import verdict as render_verdict

_WEB_PROCESS_WAIT_SECONDS = 90


class KioskRenderSelfcheck(WiseKioskCase):

    def _resume_web_process(self):
        # Re-resolves the pid rather than trusting a stale one, and
        # restarts kiosk.service unconditionally as the backstop,
        # regardless of whether a live process was found to CONT.
        status, pid = self.target.run("pgrep -f WebKitWebProcess | head -n 1")
        if status == 0 and pid.strip():
            self.target.run(f"kill -CONT {pid.strip()}")
        self.target.run("systemctl restart kiosk.service")

    def test_render_detects_frozen_process(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_render_detects_frozen_process requires role=bench, got "
                f"{WiseKioskCase.role!r}")
        self.addCleanup(self._resume_web_process)
        _wait_for_painted(self)

        # The web process appears only once the page loads after a kiosk.service
        # restart (the applied self-check's own run leaves one behind), so wait for it.
        pid = ""
        deadline = time.monotonic() + _WEB_PROCESS_WAIT_SECONDS
        while time.monotonic() < deadline:
            _status, pid = self.target.run("pgrep -f '[W]ebKitWebProcess' | head -n 1")
            pid = pid.strip()
            if pid:
                break
            time.sleep(2)
        if not pid:
            raise RuntimeError("no WebKitWebProcess found on the device")
        stop_status, _ = self.target.run(f"kill -STOP {pid}")
        if stop_status != 0:
            raise RuntimeError(f"could not STOP WebKitWebProcess (pid={pid})")

        _status, output = self.target.run(_RENDER_PROBE)
        outcome, reason = render_verdict(output.splitlines())
        if outcome != "frozen":
            self.fail(f"STOPping WebKitWebProcess did not read as frozen -- got {outcome!r} ({reason})")

        self._resume_web_process()
        _wait_for_painted(self)

        _status, output = self.target.run(_RENDER_PROBE)
        outcome, reason = render_verdict(output.splitlines())
        if outcome != "advancing":
            self.fail(f"did not return to advancing after CONT -- got {outcome!r} ({reason})")
