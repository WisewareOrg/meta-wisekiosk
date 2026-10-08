from framework.base import WiseKioskCase

from .verdict import pick_below_floor_mode, verdict as layout_verdict

_APPLIED_WAIT_SECONDS = 180


def _read_current_mode(case):
    status, output = case.target.run("DISPLAY=:0 xrandr")
    if status != 0:
        raise RuntimeError("could not read xrandr")
    _connector, current, candidate = pick_below_floor_mode(output)
    if current is None:
        raise RuntimeError("xrandr reported no current mode")
    return current, candidate


class KioskLayoutTest(WiseKioskCase):

    def test_layout_floor(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(f"test_layout_floor requires role=bench, got {WiseKioskCase.role!r}")
        self.arm_probe()
        self.wait_applied(_APPLIED_WAIT_SECONDS)

        current, _candidate = _read_current_mode(self)
        outcome, reason = layout_verdict(current)
        if outcome != "ok":
            self.fail(reason)
