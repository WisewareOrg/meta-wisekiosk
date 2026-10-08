import tempfile
import time

from framework import probe
from framework.base import WiseKioskCase

from .verdict import configuration_error_present

_CONFIG_PATH = "/data/config/config.json"
_CONFIG_BACKUP = "/data/config/config.json.pre-seed"
_APPLIED_DEADLINE_SECONDS = 90
_POLL_SECONDS = 2

_NON_JSON_BODY = "not json at all\n"


class KioskConfigErrorsTest(WiseKioskCase):

    def _write_config(self, body):
        # chmod after copyTo: copyTo preserves the local tempfile's own
        # 0600, and wisekiosk.service runs as the non-root `kiosk` user --
        # a 0600 root-owned file is unreadable to it, so the backend's own
        # staticserve.go answers 404 for a permissions error exactly as it
        # does for a missing file.
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write(body)
            f.flush()
            self.target.copyTo(f.name, _CONFIG_PATH)
        self.target.run(f"chmod 0644 {_CONFIG_PATH}")

    def _restore_config(self):
        # Idempotent: a backup already consumed by an earlier restore in
        # this same method leaves nothing to do.
        status, _ = self.target.run(f"test -f {_CONFIG_BACKUP}")
        if status != 0:
            return
        self.target.run(f"cp -a {_CONFIG_BACKUP} {_CONFIG_PATH}")
        self.target.run(f"rm -f {_CONFIG_BACKUP}")
        self.target.run("systemctl restart kiosk.service")

    def _poll_configuration_error_present(self, want, deadline):
        state = "no-probe"
        while True:
            for title in probe.title_lines(self.titles()):
                found = configuration_error_present(title)
                if found is not None:
                    state = found
                    break
            if state == want:
                return state
            if time.time() >= deadline:
                return state
            time.sleep(_POLL_SECONDS)

    def test_configuration_errors(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_configuration_errors requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self._restore_config)
        backup_status, _ = self.target.run(f"cp -a {_CONFIG_PATH} {_CONFIG_BACKUP}")
        if backup_status != 0:
            raise RuntimeError(f"could not back up {_CONFIG_PATH}")

        self.arm_probe()
        self.wait_applied(_APPLIED_DEADLINE_SECONDS)

        self._write_config(_NON_JSON_BODY)
        restart_status, _ = self.target.run("systemctl restart kiosk.service")
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service for the seed")
        deadline = time.time() + _APPLIED_DEADLINE_SECONDS
        state = self._poll_configuration_error_present(True, deadline)
        if state is not True:
            self.fail(
                f"no fault was shown within {_APPLIED_DEADLINE_SECONDS}s of the restart -- "
                f"got {state!r}")

        self._restore_config()
        self.wait_applied(_APPLIED_DEADLINE_SECONDS)
