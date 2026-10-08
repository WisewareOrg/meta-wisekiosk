import tempfile

from framework.base import WiseKioskCase

from .case import _applied_attempt

_KIOSK_CONF_PATH = "/data/config/kiosk.conf"
_KIOSK_CONF_BACKUP = "/data/config/kiosk.conf.seeded-fail-bak"
_KIOSK_URL_KEY = "KIOSK_URL"
_SEEDED_URL_LINE = f"{_KIOSK_URL_KEY}=http://localhost:1"


class KioskAppliedSelfcheck(WiseKioskCase):

    def _restore_kiosk_conf(self):
        # Idempotent: a backup already consumed by an earlier restore in
        # this same method leaves nothing to do.
        status, _ = self.target.run(f"test -f {_KIOSK_CONF_BACKUP}")
        if status != 0:
            return
        self.target.run(f"mv {_KIOSK_CONF_BACKUP} {_KIOSK_CONF_PATH}")
        self.target.run("systemctl restart kiosk.service")

    def test_applied_detects_dead_url(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_applied_detects_dead_url requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")
        self.addCleanup(self._restore_kiosk_conf)

        status, original = self.target.run(f"cat {_KIOSK_CONF_PATH}")
        if status != 0:
            raise RuntimeError(f"could not read {_KIOSK_CONF_PATH}")
        backup_status, _ = self.target.run(f"cp {_KIOSK_CONF_PATH} {_KIOSK_CONF_BACKUP}")
        if backup_status != 0:
            raise RuntimeError(f"could not back up {_KIOSK_CONF_PATH}")

        seeded_lines = [line for line in original.splitlines()
                        if not line.startswith(_KIOSK_URL_KEY + "=")]
        seeded_lines.append(_SEEDED_URL_LINE)
        seeded = "\n".join(seeded_lines) + "\n"
        with tempfile.NamedTemporaryFile("w", suffix=".conf") as seeded_file:
            seeded_file.write(seeded)
            seeded_file.flush()
            self.target.copyTo(seeded_file.name, _KIOSK_CONF_PATH)

        outcome, _sample = _applied_attempt(self)
        if outcome != "failed:error:not-app":
            self.fail(f"seeded KIOSK_URL did not fail as failed:error:not-app -- got {outcome!r}")

        self._restore_kiosk_conf()

        outcome, _sample = _applied_attempt(self)
        if outcome != "applied":
            self.fail(f"did not return to applied after restoring kiosk.conf -- got {outcome!r}")
