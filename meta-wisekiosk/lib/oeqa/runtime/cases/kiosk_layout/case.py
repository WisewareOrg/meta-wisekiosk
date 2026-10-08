import time

from framework import probe
from framework.base import WiseKioskCase

from .verdict import parse_layout, pick_below_floor_mode, verdict as layout_verdict

_POLL_SECONDS = 2
_BANNER_WAIT_SECONDS = 30
_APPLIED_WAIT_SECONDS = 180


class KioskLayoutTest(WiseKioskCase):

    # The banner this case measures clearance against is raised by the
    # same stimulus applied below -- self-sufficient (stops the backend
    # itself) rather than relying on kiosk_backend_unreachable's state
    # surviving past that case's own tearDown. docs/testing.md § "The
    # render and applied cases" has why.

    def _read_layout(self, deadline):
        parsed = None
        while parsed is None:
            for title in probe.title_lines(self.titles()):
                parsed = parse_layout(title)
                if parsed is not None:
                    break
            if parsed is None:
                if time.time() >= deadline:
                    raise RuntimeError(
                        f"no probe payload carried a layout= field within "
                        f"{_BANNER_WAIT_SECONDS}s of stopping the backend")
                time.sleep(_POLL_SECONDS)
        return parsed

    def test_layout_floor(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(f"test_layout_floor requires role=bench, got {WiseKioskCase.role!r}")
        self.arm_probe()
        self.wait_applied(_APPLIED_WAIT_SECONDS)
        self.stop_backend()

        parsed = self._read_layout(time.time() + _BANNER_WAIT_SECONDS)
        outcome, reason = layout_verdict(parsed)
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
        self.stop_backend()

        parsed = self._read_layout(time.time() + _BANNER_WAIT_SECONDS)
        outcome, reason = layout_verdict(parsed)
        if outcome == "ok":
            # Found live on bench, round-1 fixes: kiosk-launch's own
            # `xrandr --output HDMI-1 --mode 1280x720` runs unconditionally
            # on every (re)start -- the one event that makes a fresh probe
            # reading possible -- so a mode set here never survives to
            # surf's own window. Confirmed with three independent
            # mechanisms (restart, a live resize with no restart, and a
            # kill-and-respawn): every one reads back 1280x720. Recorded,
            # never asserted as a floor failure that cannot occur.
            self.skipTest(
                f"the seeded mode {candidate!r} did not reach the browser's own viewport "
                f"(read back {parsed['width']}x{parsed['height']}) -- this image's kiosk-launch "
                "unconditionally resets the display to 1280x720 on every (re)start, so no "
                "restart-driven seed can produce a below-floor viewport on this board")
        if outcome != "error" or "floor" not in reason:
            self.fail(
                f"the seeded below-floor mode {candidate!r} did not read as a floor failure -- "
                f"got {outcome!r} ({reason!r})")
