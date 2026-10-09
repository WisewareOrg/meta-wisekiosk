import time

from framework.base import WiseKioskCase, POLL_SECONDS, RESTART_TIMEOUT_SECONDS
from kiosk_applied.case import APPLIED_WAIT_SECONDS, deploy_probe, wait_applied
from kiosk_applied.verdict import read_sample

from .verdict import verdict as restart_verdict

_DEADLINE_SECONDS = 60


def _kill_surf(case):
    status, _ = case.target.run("pgrep -x surf")
    if status != 0:
        raise RuntimeError("surf is not running before the kill")
    kill_status, _ = case.target.run("kill -TERM $(pgrep -x surf)")
    if kill_status != 0:
        raise RuntimeError("could not send SIGTERM to surf")


def restart_attempt(case):
    """Arms the probe, reads the sample just before killing surf, then polls for a restarted
    verdict against it."""
    deploy_probe(case)
    restart_status, _ = case.target.run(
        "systemctl restart kiosk.service", timeout=RESTART_TIMEOUT_SECONDS)
    if restart_status != 0:
        raise RuntimeError("could not restart kiosk.service to arm the probe")
    wait_applied(case, APPLIED_WAIT_SECONDS)
    before_sample = read_sample(case.titles())

    _kill_surf(case)

    deadline = time.monotonic() + _DEADLINE_SECONDS
    after_samples = []
    while True:
        after_samples.append(read_sample(case.titles()))
        outcome, reason = restart_verdict(before_sample, after_samples)
        if outcome == "restarted" or time.monotonic() >= deadline:
            return outcome, reason
        time.sleep(POLL_SECONDS)


class KioskBrowserRestartTest(WiseKioskCase):

    def test_browser_restart(self):
        outcome, reason = restart_attempt(self)
        if outcome == "error":
            raise RuntimeError(reason)
        if outcome != "restarted":
            self.fail(f"{outcome}: {reason}")
