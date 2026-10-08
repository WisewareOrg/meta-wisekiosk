from framework.base import WiseKioskCase
from kiosk_applied.case import deploy_probe, wait_applied

from .case import read_configured_mode
from .verdict import current_mode, pick_below_floor_mode, verdict as layout_verdict

# meta-wisekiosk/recipes-core/kiosk-session/files/kiosk-launch's own --mode
# line, backed up then sed-edited here.
_LAUNCHER_PATH = "/usr/bin/kiosk-launch"
_LAUNCHER_BACKUP = "/usr/bin/kiosk-launch.selfcheck-bak"
# The launcher sets the mode before surf starts, so an applied page implies
# the mode xrandr is about to read is already settled -- same deadline
# kiosk_applied uses for its own restart-to-applied wait.
_APPLIED_WAIT_SECONDS = 90


class KioskLayoutSelfcheck(WiseKioskCase):

    def _restore_launcher(self):
        # Idempotent: a backup already consumed by an earlier restore in
        # this same method leaves nothing to do.
        status, _ = self.target.run(f"test -f {_LAUNCHER_BACKUP}")
        if status != 0:
            return
        mv_status, _ = self.target.run(f"mv {_LAUNCHER_BACKUP} {_LAUNCHER_PATH}")
        if mv_status != 0:
            raise RuntimeError(f"could not restore {_LAUNCHER_PATH} from its backup")
        restart_status, _ = self.target.run("systemctl restart kiosk.service")
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service after restoring the launcher")
        wait_applied(self, _APPLIED_WAIT_SECONDS)

    def _read_verdict(self):
        status, xrandr_output = self.target.run("DISPLAY=:0 xrandr")
        if status != 0:
            raise RuntimeError("could not read xrandr")
        configured_mode = read_configured_mode(self)
        return layout_verdict(xrandr_output, configured_mode)

    def test_layout_detects_below_floor_mode(self):
        status, output = self.target.run("DISPLAY=:0 xrandr")
        if status != 0:
            raise RuntimeError("could not read xrandr")
        connector, _current_mode, candidate = pick_below_floor_mode(output)
        if candidate is None:
            self.skipTest(
                f"{connector!r} offers no mode below the 1280x720 floor -- cannot seed one")

        deploy_probe(self)
        self.addCleanup(self._restore_launcher)
        backup_status, _ = self.target.run(f"cp -a {_LAUNCHER_PATH} {_LAUNCHER_BACKUP}")
        if backup_status != 0:
            raise RuntimeError(f"could not back up {_LAUNCHER_PATH}")
        sed_status, _ = self.target.run(
            f"sed -i 's/--mode 1280x720/--mode {candidate}/' {_LAUNCHER_PATH}")
        if sed_status != 0:
            raise RuntimeError(f"could not edit {_LAUNCHER_PATH}")
        landed_status, landed_count = self.target.run(
            f"grep -c -- '--mode {candidate}' {_LAUNCHER_PATH}")
        if landed_status != 0 or landed_count.strip() == "0":
            raise RuntimeError(f"the seeded --mode {candidate} did not land in {_LAUNCHER_PATH}")

        restart_status, _ = self.target.run("systemctl restart kiosk.service")
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service after seeding the launcher")
        wait_applied(self, _APPLIED_WAIT_SECONDS)

        status, xrandr_output = self.target.run("DISPLAY=:0 xrandr")
        if status != 0:
            raise RuntimeError("could not read xrandr")
        landed_mode = current_mode(xrandr_output)
        if landed_mode != candidate:
            self.fail(f"seed did not land: xrandr reports {landed_mode!r}")
        configured_mode = read_configured_mode(self)
        outcome, reason = layout_verdict(xrandr_output, configured_mode)
        if outcome != "below-floor":
            self.fail(
                f"the seeded launcher mode {candidate!r} did not read as below-floor -- "
                f"got {outcome!r} ({reason!r})")

        self._restore_launcher()

        outcome, reason = self._read_verdict()
        if outcome != "ok":
            self.fail(
                f"did not return to a floor-ok, matching mode after restoring {_LAUNCHER_PATH} -- "
                f"got {outcome!r} ({reason!r})")
