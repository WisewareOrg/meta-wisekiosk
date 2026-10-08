import time
from pathlib import Path

from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS
from kiosk_applied.verdict import read_sample

# The one probe script (design §2.5: "one probe script, one record format"),
# owned by kiosk_applied -- referenced here rather than duplicated.
_PROBE_SRC = Path(__file__).resolve().parents[1] / "kiosk_applied" / "probe.js"

_DEADLINE_SECONDS = 60
_POLL_SECONDS = 2


def _deploy_probe(case):
    # Deliberately not case.arm_probe(): that method also restarts
    # kiosk.service, which here would be the stimulus itself, run too
    # early. The deploy-only step every probe-reading case repeated is
    # just mkdir+copyTo -- this case's own kill is the restart trigger.
    case.addCleanup(case.target.run, "rm -f /home/root/.surf/script.js")
    mkdir_status, _ = case.target.run(
        "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
    if mkdir_status != 0:
        raise RuntimeError("could not arm the probe (mkdir)")
    case.target.copyTo(str(_PROBE_SRC), "/home/root/.surf/script.js")


def _kill_surf(case):
    status, _ = case.target.run("pgrep -x surf")
    if status != 0:
        raise RuntimeError("surf is not running before the kill")
    kill_status, _ = case.target.run("kill -TERM $(pgrep -x surf)")
    if kill_status != 0:
        raise RuntimeError("could not send SIGTERM to surf")


def _wait_applied_or_fail(case, deadline_seconds):
    deadline = time.time() + deadline_seconds
    sample = None
    while True:
        sample = read_sample(case.titles())
        if sample and sample["state"] == "applied":
            return
        if time.time() >= deadline:
            break
        time.sleep(_POLL_SECONDS)
    if sample is None:
        case.fail(
            f"no probe payload within {deadline_seconds}s -- kiosk.service did not restart surf")
    case.fail(f"page not applied within {deadline_seconds}s -- state={sample['state']}")


class KioskBrowserRestartTest(WiseKioskCase):

    def test_browser_restart(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_browser_restart requires role=bench, got {WiseKioskCase.role!r}")
        _deploy_probe(self)
        _kill_surf(self)
        _wait_applied_or_fail(self, _DEADLINE_SECONDS)
