from framework.base import WiseKioskCase

from .case import _APPLIED_WAIT_SECONDS, _read_current_mode
from .verdict import pick_below_floor_mode, verdict as layout_verdict

# The appliance's own file (meta-wisekiosk/recipes-core/kiosk-session/files/
# kiosk-launch's own `xrandr --output HDMI-1 --mode 1280x720` line) -- the
# appliance seeding its own fault, never a live xrandr call the launcher
# itself would undo on the very next (re)start.
_LAUNCHER_PATH = "/usr/bin/kiosk-launch"
_LAUNCHER_BACKUP = "/usr/bin/kiosk-launch.pre-seed"


class KioskLayoutSelfcheck(WiseKioskCase):

    def _restore_launcher(self):
        # Idempotent: a backup already consumed by an earlier restore in
        # this same method leaves nothing to do.
        status, _ = self.target.run(f"test -f {_LAUNCHER_BACKUP}")
        if status != 0:
            return
        self.target.run(f"mv {_LAUNCHER_BACKUP} {_LAUNCHER_PATH}")
        self.target.run("systemctl restart kiosk.service")

    def test_layout_detects_below_floor_mode(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_layout_detects_below_floor_mode requires role=bench, got "
                f"{WiseKioskCase.role!r}")
        status, output = self.target.run("DISPLAY=:0 xrandr")
        if status != 0:
            raise RuntimeError("could not read xrandr")
        connector, _current_mode, candidate = pick_below_floor_mode(output)
        if candidate is None:
            self.skipTest(
                f"{connector!r} offers no mode below the 1280x720 floor -- cannot seed one")

        self.addCleanup(self._restore_launcher)
        backup_status, _ = self.target.run(f"cp -a {_LAUNCHER_PATH} {_LAUNCHER_BACKUP}")
        if backup_status != 0:
            raise RuntimeError(f"could not back up {_LAUNCHER_PATH}")
        sed_status, _ = self.target.run(
            f"sed -i 's/--mode 1280x720/--mode {candidate}/' {_LAUNCHER_PATH}")
        if sed_status != 0:
            raise RuntimeError(f"could not edit {_LAUNCHER_PATH}")

        self.arm_probe()
        self.wait_applied(_APPLIED_WAIT_SECONDS)

        current_after, _candidate2 = _read_current_mode(self)
        outcome, reason = layout_verdict(current_after)
        if outcome != "error" or "floor" not in reason:
            self.fail(
                f"the seeded launcher mode {candidate!r} did not read as a floor failure -- "
                f"got {outcome!r} ({reason!r}), read back {current_after!r}")

        self._restore_launcher()
        self.wait_applied(_APPLIED_WAIT_SECONDS)

        current_restored, _candidate3 = _read_current_mode(self)
        outcome, reason = layout_verdict(current_restored)
        if outcome != "ok":
            self.fail(
                f"did not return to a floor-ok mode after restoring {_LAUNCHER_PATH} -- "
                f"got {outcome!r} ({reason!r}), read back {current_restored!r}")
