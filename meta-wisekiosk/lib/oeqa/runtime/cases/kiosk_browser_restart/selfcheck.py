import tempfile
import time

from framework.base import WiseKioskCase

from .case import _DEADLINE_SECONDS, _deploy_probe, _kill_surf, _wait_applied_or_fail

# The seed that proves the check itself, not the feature: Restart=always is
# the unit's own shipped policy (test_browser_restart proves it live), so
# this drop-in exists only to show the check would catch it if that policy
# were ever broken.
_DROPIN_DIR = "/etc/systemd/system/kiosk.service.d"
_DROPIN_PATH = _DROPIN_DIR + "/zz-acceptance-restart.conf"
_DROPIN_BODY = "[Service]\nRestart=no\n"
_SEEDED_FAIL_DEADLINE_SECONDS = 60
_POLL_SECONDS = 2


class KioskBrowserRestartSelfcheck(WiseKioskCase):

    def _remove_dropin(self):
        self.target.run(f"rm -f {_DROPIN_PATH}")
        self.target.run("systemctl daemon-reload")
        self.target.run("systemctl start kiosk.service")

    def test_browser_restart_detects_broken_policy(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_browser_restart_detects_broken_policy requires role=bench, got "
                f"{WiseKioskCase.role!r}")
        self.addCleanup(self._remove_dropin)
        _deploy_probe(self)

        mkdir_status, _ = self.target.run(f"mkdir -p {_DROPIN_DIR}")
        if mkdir_status != 0:
            raise RuntimeError(f"could not create {_DROPIN_DIR}")
        with tempfile.NamedTemporaryFile("w", suffix=".conf") as f:
            f.write(_DROPIN_BODY)
            f.flush()
            self.target.copyTo(f.name, _DROPIN_PATH)
        reload_status, _ = self.target.run("systemctl daemon-reload")
        if reload_status != 0:
            raise RuntimeError("could not daemon-reload after writing the drop-in")

        _kill_surf(self)

        # The red: kiosk.service stays down for the whole deadline under
        # Restart=no, where test_browser_restart's own run proves it would
        # not, live, under the real Restart=always policy.
        deadline = time.time() + _SEEDED_FAIL_DEADLINE_SECONDS
        while True:
            _status, active = self.target.run("systemctl is-active kiosk.service")
            if active.strip() == "active":
                self.fail(
                    "kiosk.service came back despite the Restart=no drop-in -- "
                    "the seed did not take effect")
            if time.time() >= deadline:
                break
            time.sleep(_POLL_SECONDS)

        # The green: remove the seed, start the unit (the probe deployed
        # above is still in place -- surf picks it up on this start).
        self._remove_dropin()
        _wait_applied_or_fail(self, _DEADLINE_SECONDS)
