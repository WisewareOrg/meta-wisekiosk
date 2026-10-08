import time
from framework.base import WiseKioskCase

from .verdict import verdict as render_verdict

# The render check's default crop, ported from tools/kiosk-render-check.sh --
# docs/testing.md § "The render and applied cases" has the why.
_RENDER_CROP = "560x300+220+20"
_RENDER_PROBE = (
    'if ! command -v import > /dev/null 2>&1; then echo "cap import=0"; exit 0; fi\n'
    "F=/tmp/render-check.$$\n"
    "grab() {\n"
    "    n=$1\n"
    '    DISPLAY=:0 import -window root -crop "%s" +repage "$F.$n.png" > /dev/null 2>"$F.$n.err"\n'
    "    rc=$?\n"
    '    if [ -f "$F.$n.png" ]; then\n'
    '        b=$(wc -c < "$F.$n.png")\n'
    '        m=$(md5sum < "$F.$n.png" | cut -d\' \' -f1)\n'
    "    else\n"
    "        b=0\n"
    "        m=none\n"
    "    fi\n"
    '    err=$(tr \'\\n\' \' \' < "$F.$n.err" 2>/dev/null | tr -s \' \' \'_\')\n'
    '    echo "frame $n rc=$rc bytes=$b md5=$m err=${err:-none}"\n'
    "}\n"
    "grab 1\n"
    "sleep 3\n"
    "grab 2\n"
    'if command -v identify > /dev/null 2>&1 && [ -f "$F.2.png" ]; then\n'
    "    identify -format 'blank min=%%[fx:minima*255] max=%%[fx:maxima*255] "
    "mean=%%[fx:mean*255]\\n' \"$F.2.png\" 2>/dev/null\n"
    "fi\n"
    'rm -f "$F.1.png" "$F.2.png" "$F.1.err" "$F.2.err"\n'
) % _RENDER_CROP


_WEB_PROCESS_WAIT_SECONDS = 90
_PAINT_WAIT_SECONDS = 180
_SETTLE_SECONDS = 15


class KioskRenderTest(WiseKioskCase):

    def _wait_for_painted(self):
        # A page that is still loading after a kiosk.service restart captures as a
        # uniform region; the two-frame check is meaningful only once it has painted.
        deadline = time.monotonic() + _PAINT_WAIT_SECONDS
        while True:
            _status, output = self.target.run(_RENDER_PROBE)
            outcome, reason = render_verdict(output.splitlines())
            if not (outcome == "error" and "uniform" in reason):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"the page did not paint within {_PAINT_WAIT_SECONDS}s: {reason}")
            time.sleep(5)
        time.sleep(_SETTLE_SECONDS)

    def test_render_advancing(self):
        self._wait_for_painted()
        _status, output = self.target.run(_RENDER_PROBE)
        outcome, reason = render_verdict(output.splitlines())
        if outcome == "advancing":
            return
        if outcome == "frozen":
            self.fail(reason)
        raise RuntimeError(reason)

    def _resume_web_process(self):
        # Re-resolves the pid rather than trusting a stale one, and
        # restarts kiosk.service unconditionally as the backstop,
        # regardless of whether a live process was found to CONT.
        status, pid = self.target.run("pgrep -f WebKitWebProcess | head -n 1")
        if status == 0 and pid.strip():
            self.target.run(f"kill -CONT {pid.strip()}")
        self.target.run("systemctl restart kiosk.service")

    def test_render_seeded_fail(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_render_seeded_fail requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self._resume_web_process)
        self._wait_for_painted()

        # The web process appears only once the page loads after a kiosk.service
        # restart (the applied case's seeded run leaves one behind), so wait for it.
        pid = ""
        deadline = time.monotonic() + _WEB_PROCESS_WAIT_SECONDS
        while time.monotonic() < deadline:
            _status, pid = self.target.run("pgrep -f '[W]ebKitWebProcess' | head -n 1")
            pid = pid.strip()
            if pid:
                break
            time.sleep(2)
        if not pid:
            raise RuntimeError("no WebKitWebProcess found on the device")
        stop_status, _ = self.target.run(f"kill -STOP {pid}")
        if stop_status != 0:
            raise RuntimeError(f"could not STOP WebKitWebProcess (pid={pid})")

        _status, output = self.target.run(_RENDER_PROBE)
        outcome, reason = render_verdict(output.splitlines())
        if outcome != "frozen":
            self.fail(f"STOPping WebKitWebProcess did not read as frozen -- got {outcome!r} ({reason})")

        self._resume_web_process()
        self._wait_for_painted()

        _status, output = self.target.run(_RENDER_PROBE)
        outcome, reason = render_verdict(output.splitlines())
        if outcome != "advancing":
            self.fail(f"did not return to advancing after CONT -- got {outcome!r} ({reason})")
