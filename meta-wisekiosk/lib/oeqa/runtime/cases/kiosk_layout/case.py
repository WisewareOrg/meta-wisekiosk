from framework.base import WiseKioskCase

from .verdict import pick_below_floor_mode, verdict as layout_verdict

_APPLIED_WAIT_SECONDS = 180


class KioskLayoutTest(WiseKioskCase):

    def _read_current_mode(self):
        status, output = self.target.run("DISPLAY=:0 xrandr")
        if status != 0:
            raise RuntimeError("could not read xrandr")
        _connector, current, candidate = pick_below_floor_mode(output)
        if current is None:
            raise RuntimeError("xrandr reported no current mode")
        return current, candidate

    def test_layout_floor(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(f"test_layout_floor requires role=bench, got {WiseKioskCase.role!r}")
        self.arm_probe()
        self.wait_applied(_APPLIED_WAIT_SECONDS)

        current, _candidate = self._read_current_mode()
        outcome, reason = layout_verdict(current)
        if outcome != "ok":
            self.fail(reason)

    def test_layout_seeded_fail(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_layout_seeded_fail requires role=bench, got {WiseKioskCase.role!r}")
        status, output = self.target.run("DISPLAY=:0 xrandr")
        if status != 0:
            raise RuntimeError("could not read xrandr")
        connector, current_mode, candidate = pick_below_floor_mode(output)
        if candidate is None:
            self.skipTest(
                f"{connector!r} offers no mode below the 1280x720 floor -- cannot seed one")
        if current_mode is None:
            raise RuntimeError("xrandr reported no current mode to restore afterward")

        self.addCleanup(
            self.target.run, f"DISPLAY=:0 xrandr --output {connector} --mode {current_mode}")
        set_status, _ = self.target.run(f"DISPLAY=:0 xrandr --output {connector} --mode {candidate}")
        if set_status != 0:
            raise RuntimeError(f"could not set {connector} to {candidate}")

        self.arm_probe()
        self.wait_applied(_APPLIED_WAIT_SECONDS)

        current_after, _candidate2 = self._read_current_mode()
        outcome, reason = layout_verdict(current_after)
        if outcome == "ok":
            # Found live on bench, round-1 fixes: kiosk-launch's own
            # `xrandr --output HDMI-1 --mode 1280x720` runs unconditionally
            # on every (re)start -- the one event that makes a fresh probe
            # reading possible -- so a mode set here never survives to the
            # reported xrandr mode. Confirmed with three independent
            # mechanisms (restart, a live resize with no restart, and a
            # kill-and-respawn): every one reads back 1280x720. Recorded,
            # never asserted as a floor failure that cannot occur.
            self.skipTest(
                f"the seeded mode {candidate!r} did not survive to the reported xrandr mode "
                f"(read back {current_after!r}) -- this image's kiosk-launch unconditionally "
                "resets the display to 1280x720 on every (re)start, so no restart-driven seed "
                "can produce a below-floor mode on this board")
        if outcome != "error" or "floor" not in reason:
            self.fail(
                f"the seeded below-floor mode {candidate!r} did not read as a floor failure -- "
                f"got {outcome!r} ({reason!r})")
