import tempfile

from framework.base import POLL_ATTEMPT_TIMEOUT_SECONDS, WiseKioskCase

from .case import applied_attempt

_KIOSK_CONF_PATH = "/data/config/kiosk.conf"
_KIOSK_CONF_BACKUP = "/data/config/kiosk.conf.selfcheck-bak"
_KIOSK_URL_KEY = "KIOSK_URL"
_SEEDED_URL_LINE = f"{_KIOSK_URL_KEY}=http://localhost:1"


class KioskAppliedSelfcheck(WiseKioskCase):

    def _restore_kiosk_conf(self):
        # Idempotent: a backup already consumed by an earlier restore in
        # this same method leaves nothing to do.
        status, _ = self.target.run(f"test -f {_KIOSK_CONF_BACKUP}")
        if status != 0:
            return
        mv_status, _ = self.target.run(f"mv {_KIOSK_CONF_BACKUP} {_KIOSK_CONF_PATH}")
        if mv_status != 0:
            raise RuntimeError(f"could not restore {_KIOSK_CONF_PATH} from its backup")
        restart_status, _ = self.target.run(
            "systemctl restart kiosk.service", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service after restoring kiosk.conf")

    def test_applied_detects_dead_url(self):
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

        readback_status, readback = self.target.run(f"cat {_KIOSK_CONF_PATH}")
        if readback_status != 0 or _SEEDED_URL_LINE not in readback.splitlines():
            raise RuntimeError(f"the seeded {_KIOSK_URL_KEY} did not land in {_KIOSK_CONF_PATH}")

        outcome, reason, _sample = applied_attempt(self)
        if (outcome, reason) != ("failed", "error:not-app"):
            self.fail(
                f"seeded KIOSK_URL did not fail as failed:error:not-app -- got {outcome}:{reason!r}")

        self._restore_kiosk_conf()

        outcome, reason, _sample = applied_attempt(self)
        if outcome != "applied":
            self.fail(f"did not return to applied after restoring kiosk.conf -- got {outcome}:{reason!r}")
