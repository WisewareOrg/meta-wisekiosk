import tempfile

from framework.base import WiseKioskCase

from .case import restart_attempt

# Restart=no drop-in; _remove_dropin restores it.
_DROPIN_DIR = "/etc/systemd/system/kiosk.service.d"
_DROPIN_PATH = _DROPIN_DIR + "/zz-selfcheck.conf"
_DROPIN_BODY = "[Service]\nRestart=no\n"


class KioskBrowserRestartSelfcheck(WiseKioskCase):

    def _remove_dropin(self):
        rm_status, _ = self.target.run(f"rm -f {_DROPIN_PATH}")
        if rm_status != 0:
            raise RuntimeError(f"could not remove {_DROPIN_PATH}")
        reload_status, _ = self.target.run("systemctl daemon-reload")
        if reload_status != 0:
            raise RuntimeError("could not daemon-reload after removing the drop-in")
        start_status, _ = self.target.run("systemctl start kiosk.service")
        if start_status != 0:
            raise RuntimeError("could not start kiosk.service after removing the drop-in")

    def test_browser_restart_detects_broken_policy(self):
        self.addCleanup(self._remove_dropin)

        mkdir_status, _ = self.target.run(f"mkdir -p {_DROPIN_DIR}")
        if mkdir_status != 0:
            raise RuntimeError(f"could not create {_DROPIN_DIR}")
        with tempfile.NamedTemporaryFile("w", suffix=".conf") as dropin_file:
            dropin_file.write(_DROPIN_BODY)
            dropin_file.flush()
            self.target.copyTo(dropin_file.name, _DROPIN_PATH)
        reload_status, _ = self.target.run("systemctl daemon-reload")
        if reload_status != 0:
            raise RuntimeError("could not daemon-reload after writing the drop-in")
        readback_status, readback = self.target.run("systemctl show -p Restart --value kiosk.service")
        if readback_status != 0 or readback.strip() != "no":
            raise RuntimeError(
                f"the Restart=no drop-in did not land -- systemctl reads Restart={readback.strip()!r}")

        outcome, reason = restart_attempt(self)
        if outcome != "not-restarted":
            self.fail(f"Restart=no did not read as not-restarted -- got {outcome!r} ({reason!r})")

        self._remove_dropin()

        outcome, reason = restart_attempt(self)
        if outcome != "restarted":
            self.fail(
                f"did not return to restarted after removing the drop-in -- got {outcome!r} ({reason!r})")
