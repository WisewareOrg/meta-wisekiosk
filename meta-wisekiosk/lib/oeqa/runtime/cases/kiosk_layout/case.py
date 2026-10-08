from framework.base import WiseKioskCase

from .verdict import verdict as layout_verdict

_LAUNCHER_PATH = "/usr/bin/kiosk-launch"


def read_configured_mode(case):
    status, output = case.target.run(
        f"grep -o -- '--mode [0-9]*x[0-9]*' {_LAUNCHER_PATH} | head -n 1 | cut -d' ' -f2")
    if status != 0 or not output.strip():
        raise RuntimeError(f"could not read the configured mode from {_LAUNCHER_PATH}")
    return output.strip()


class KioskLayoutTest(WiseKioskCase):

    def test_layout_floor(self):
        status, xrandr_output = self.target.run("DISPLAY=:0 xrandr")
        if status != 0:
            raise RuntimeError("could not read xrandr")
        configured_mode = read_configured_mode(self)
        outcome, reason = layout_verdict(xrandr_output, configured_mode)
        if outcome == "error":
            raise RuntimeError(reason)
        if outcome != "ok":
            self.fail(reason)
