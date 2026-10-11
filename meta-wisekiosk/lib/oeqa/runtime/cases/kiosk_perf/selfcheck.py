import tempfile

from framework.base import RESTART_TIMEOUT_SECONDS, WiseKioskCase
from kiosk_applied.case import PROBE_SRC

from . import verdict
from .case import measure

_SCRIPT = "/home/root/.surf/script.js"
_SHORT_WINDOW_MS = 30000
# The probe's start of its rAF chain; the frozen seed drops the chain.
_RAF_START = "requestAnimationFrame(tick);\n  report();"


class KioskPerfSelfcheck(WiseKioskCase):

    def _load(self, source):
        self.addCleanup(self.target.run, "systemctl restart kiosk.service",
                        timeout=RESTART_TIMEOUT_SECONDS)
        self.addCleanup(self.target.run, f"rm -f {_SCRIPT}")
        self.target.run("mkdir -p /home/root/.surf")
        with tempfile.NamedTemporaryFile("w", suffix=".js") as script:
            script.write(source)
            script.flush()
            self.target.copyTo(script.name, _SCRIPT)
        status, _ = self.target.run("systemctl restart kiosk.service", timeout=RESTART_TIMEOUT_SECONDS)
        if status != 0:
            raise RuntimeError("could not restart kiosk.service with the seeded probe")

    def test_perf_detects_frozen_page(self):
        source = PROBE_SRC.read_text()
        if _RAF_START not in source:
            raise RuntimeError("probe.js no longer starts its rAF chain the way the seed removes it")
        self._load(source.replace(_RAF_START, "report();"))
        start, end, *_ = measure(self, _SHORT_WINDOW_MS)
        with self.assertRaises(ValueError):
            verdict.metrics(start, end)

    def test_perf_voids_on_mismatched_expected(self):
        self._load(PROBE_SRC.read_text())
        start, end, *_ = measure(self, _SHORT_WINDOW_MS)
        own = {key: start[key] for key in ("cards", "faulted", "unreachable")}
        self.assertEqual(verdict.validity(start, end, own)[0], "valid")
        self.assertEqual(verdict.validity(start, end, dict(own, cards="9/9"))[0], "void")
