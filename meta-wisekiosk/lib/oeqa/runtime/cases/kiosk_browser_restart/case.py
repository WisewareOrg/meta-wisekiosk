import tempfile
import time
from pathlib import Path

from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS
from kiosk_applied.verdict import read_sample

# The one probe script (design §2.5: "one probe script, one record format"),
# owned by kiosk_applied -- referenced here rather than duplicated.
_PROBE_SRC = Path(__file__).resolve().parents[1] / "kiosk_applied" / "probe.js"

_DEADLINE_SECONDS = 60
_POLL_SECONDS = 2

# The seed that proves the check itself, not the feature: Restart=always is
# the unit's own shipped policy (test_browser_restart proves it live), so
# this drop-in exists only to show the case would catch it if that policy
# were ever broken.
_DROPIN_DIR = "/etc/systemd/system/kiosk.service.d"
_DROPIN_PATH = _DROPIN_DIR + "/zz-acceptance-restart.conf"
_DROPIN_BODY = "[Service]\nRestart=no\n"
_SEEDED_FAIL_DEADLINE_SECONDS = 60


class KioskBrowserRestartTest(WiseKioskCase):

    def _deploy_probe(self):
        # Deliberately not self.arm_probe(): that method also restarts
        # kiosk.service, which here would be the stimulus itself, run too
        # early. The deploy-only step every probe-reading case repeated is
        # just mkdir+copyTo -- this case's own kill is the restart trigger.
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")
        mkdir_status, _ = self.target.run(
            "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if mkdir_status != 0:
            raise RuntimeError("could not arm the probe (mkdir)")
        self.target.copyTo(str(_PROBE_SRC), "/home/root/.surf/script.js")

    def _kill_surf(self):
        status, _ = self.target.run("pgrep -x surf")
        if status != 0:
            raise RuntimeError("surf is not running before the kill")
        kill_status, _ = self.target.run("kill -TERM $(pgrep -x surf)")
        if kill_status != 0:
            raise RuntimeError("could not send SIGTERM to surf")

    def _wait_applied_or_fail(self, deadline_seconds):
        deadline = time.time() + deadline_seconds
        sample = None
        while True:
            sample = read_sample(self.titles())
            if sample and sample["state"] == "applied":
                return
            if time.time() >= deadline:
                break
            time.sleep(_POLL_SECONDS)
        if sample is None:
            self.fail(
                f"no probe payload within {deadline_seconds}s -- kiosk.service did not restart surf")
        self.fail(f"page not applied within {deadline_seconds}s -- state={sample['state']}")

    def test_browser_restart(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_browser_restart requires role=bench, got {WiseKioskCase.role!r}")
        self._deploy_probe()
        self._kill_surf()
        self._wait_applied_or_fail(_DEADLINE_SECONDS)

    def _remove_dropin(self):
        self.target.run(f"rm -f {_DROPIN_PATH}")
        self.target.run("systemctl daemon-reload")
        self.target.run("systemctl start kiosk.service")

    def test_browser_restart_seeded_fail(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_browser_restart_seeded_fail requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self._remove_dropin)
        self._deploy_probe()

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

        self._kill_surf()

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
        self._wait_applied_or_fail(_DEADLINE_SECONDS)
