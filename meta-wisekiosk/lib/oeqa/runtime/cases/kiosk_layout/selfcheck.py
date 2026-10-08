from framework.base import WiseKioskCase, RESTART_TIMEOUT_SECONDS
from kiosk_applied.case import APPLIED_WAIT_SECONDS, deploy_probe, wait_applied

from .case import LAUNCHER_PATH, launcher_mode
from .verdict import MIN_HEIGHT, MIN_WIDTH, current_mode, pick_below_floor_mode, verdict as layout_verdict

_LAUNCHER_BACKUP = "/usr/bin/kiosk-launch.selfcheck-bak"


class KioskLayoutSelfcheck(WiseKioskCase):

    def _restore_launcher(self):
        # Idempotent: a backup already consumed by an earlier restore in
        # this same method leaves nothing to do.
        status, _ = self.target.run(f"test -f {_LAUNCHER_BACKUP}")
        if status != 0:
            return
        mv_status, _ = self.target.run(f"mv {_LAUNCHER_BACKUP} {LAUNCHER_PATH}")
        if mv_status != 0:
            raise RuntimeError(f"could not restore {LAUNCHER_PATH} from its backup")
        restart_status, _ = self.target.run(
            "systemctl restart kiosk.service", timeout=RESTART_TIMEOUT_SECONDS)
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service after restoring the launcher")
        wait_applied(self, APPLIED_WAIT_SECONDS)

    def _read_verdict(self):
        status, xrandr_output = self.target.run("DISPLAY=:0 xrandr")
        if status != 0:
            raise RuntimeError("could not read xrandr")
        configured_mode = launcher_mode(self)
        outcome, reason = layout_verdict(xrandr_output, configured_mode)
        return xrandr_output, outcome, reason

    def test_layout_detects_below_floor_mode(self):
        status, output = self.target.run("DISPLAY=:0 xrandr")
        if status != 0:
            raise RuntimeError("could not read xrandr")
        connector, _current_mode, candidate = pick_below_floor_mode(output)
        if candidate is None:
            self.skipTest(
                f"{connector!r} offers no mode below the {MIN_WIDTH}x{MIN_HEIGHT} floor -- "
                f"cannot seed one")

        deploy_probe(self)
        self.addCleanup(self._restore_launcher)
        backup_status, _ = self.target.run(f"cp -a {LAUNCHER_PATH} {_LAUNCHER_BACKUP}")
        if backup_status != 0:
            raise RuntimeError(f"could not back up {LAUNCHER_PATH}")
        configured_mode = launcher_mode(self)
        sed_status, _ = self.target.run(
            f"sed -i 's/--mode {configured_mode}/--mode {candidate}/' {LAUNCHER_PATH}")
        if sed_status != 0:
            raise RuntimeError(f"could not edit {LAUNCHER_PATH}")
        landed_status, landed_count = self.target.run(
            f"grep -c -- '--mode {candidate}' {LAUNCHER_PATH}")
        if landed_status != 0 or landed_count.strip() == "0":
            raise RuntimeError(f"the seeded --mode {candidate} did not land in {LAUNCHER_PATH}")

        restart_status, _ = self.target.run(
            "systemctl restart kiosk.service", timeout=RESTART_TIMEOUT_SECONDS)
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service after seeding the launcher")
        wait_applied(self, APPLIED_WAIT_SECONDS)

        xrandr_output, outcome, reason = self._read_verdict()
        landed_mode = current_mode(xrandr_output)
        if landed_mode != candidate:
            self.fail(f"seed did not land: xrandr reports {landed_mode!r}")
        if outcome != "below-floor":
            self.fail(
                f"the seeded launcher mode {candidate!r} did not read as below-floor -- "
                f"got {outcome!r} ({reason!r})")

        self._restore_launcher()

        _xrandr_output, outcome, reason = self._read_verdict()
        if outcome != "ok":
            self.fail(
                f"did not return to a floor-ok, matching mode after restoring {LAUNCHER_PATH} -- "
                f"got {outcome!r} ({reason!r})")
