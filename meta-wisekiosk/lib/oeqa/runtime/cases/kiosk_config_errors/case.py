import json
import tempfile
import time

from framework import probe
from framework.base import WiseKioskCase

from .verdict import parse_configuration_error

_CONFIG_PATH = "/data/config/config.json"
_CONFIG_BACKUP = "/data/config/config.json.pre-seed"
_APPLIED_DEADLINE_SECONDS = 90
_POLL_SECONDS = 2

_NON_JSON_BODY = "not json at all\n"
# Schema-invalid per frontend/src/config/schema.json's own "required":
# ["region", "module"] on a module placement -- this one carries neither.
_SCHEMA_INVALID_BODY = json.dumps({"modules": [{}]})

# (classification, replacement body or None for "move it aside") -- the
# ticket's own three seeds, in order.
_SEEDS = (
    ("absent", None),
    ("unparsable", _NON_JSON_BODY),
    ("rejected", _SCHEMA_INVALID_BODY),
)


class KioskConfigErrorsTest(WiseKioskCase):

    def _write_config(self, body):
        # chmod after copyTo: copyTo preserves the local tempfile's own
        # 0600, and wisekiosk.service runs as the non-root `kiosk` user --
        # a 0600 root-owned file is unreadable to it, so the backend's own
        # staticserve.go answers 404 for a permissions error exactly as it
        # does for a missing file, misreading as "absent" (found live on
        # bench, round-1 fixes).
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

    def _poll_configuration_error(self, want, deadline):
        state = "no-probe"
        while True:
            for title in probe.title_lines(self.titles()):
                found = parse_configuration_error(title)
                if found is not None:
                    state = found
                    break
                if probe.fields(title) is not None:
                    state = "absent-field"
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

        deadline = time.time() + _APPLIED_DEADLINE_SECONDS
        state = self._poll_configuration_error("absent-field", deadline)
        if state != "absent-field":
            self.fail(
                f"a configuration-error={state!r} is present on the healthy board config -- "
                "expected none")

        for kind, body in _SEEDS:
            if body is None:
                rm_status, _ = self.target.run(f"rm -f {_CONFIG_PATH}")
                if rm_status != 0:
                    raise RuntimeError(f"could not move {_CONFIG_PATH} aside for the {kind!r} seed")
            else:
                self._write_config(body)
            restart_status, _ = self.target.run("systemctl restart kiosk.service")
            if restart_status != 0:
                raise RuntimeError(f"could not restart kiosk.service for the {kind!r} seed")
            deadline = time.time() + _APPLIED_DEADLINE_SECONDS
            state = self._poll_configuration_error(kind, deadline)
            if state != kind:
                self.fail(
                    f"configuration-error did not read {kind!r} within "
                    f"{_APPLIED_DEADLINE_SECONDS}s of the restart -- got {state!r}")

        self._restore_config()
        self.wait_applied(_APPLIED_DEADLINE_SECONDS)
