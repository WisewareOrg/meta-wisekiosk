import time
from pathlib import Path

from framework import record
from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS

from .verdict import read_sample, verdict as applied_verdict

_PROBE_SRC = Path(__file__).resolve().parent / "probe.js"

_APPLIED_DEADLINE_SECONDS = 90
_APPLIED_POLL_SECONDS = 2
_APPLIED_ATTEMPTS = 2


def _read_applied_sample(case):
    return read_sample(case.titles())


def _applied_attempt(case):
    # A deploy failure here takes the same retry path as a probe
    # failure: the caller only ever sees an "error:*" outcome. Deploy
    # (mkdir, copyTo) runs before the clock and is unbounded; the 90 s
    # deadline starts when the restart is issued, matching the
    # ticket's "applied within 90 s of the restart" -- the restart's
    # own duration counts, and the poll gets the remainder.
    try:
        mkdir_status, _ = case.target.run(
            "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if mkdir_status != 0:
            return "error:deploy", None
        case.target.copyTo(str(_PROBE_SRC), "/home/root/.surf/script.js")
        deadline = time.time() + _APPLIED_DEADLINE_SECONDS
        restart_status, _ = case.target.run(
            "systemctl restart kiosk.service", timeout=int(max(1, deadline - time.time())))
        if restart_status != 0:
            return "error:deploy", None
    except AssertionError:
        return "error:deploy", None

    samples = []
    while True:
        samples.append(_read_applied_sample(case))
        outcome = applied_verdict(samples)
        if outcome == "applied":
            return outcome, samples[-1]
        if time.time() >= deadline:
            break
        time.sleep(_APPLIED_POLL_SECONDS)

    outcome = applied_verdict(samples)
    real = [sample for sample in samples if sample is not None]
    return outcome, (real[-1] if real else None)


class KioskAppliedTest(WiseKioskCase):

    def test_page_applied(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_page_applied requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")

        outcome, sample = None, None
        for attempt in range(_APPLIED_ATTEMPTS):
            outcome, sample = _applied_attempt(self)
            if not outcome.startswith("error:"):
                break
        else:
            # The declared transport kind: run.sh's own infrastructure-
            # failure path reads this exact state from the page line.
            self.tc.extraresults[record.RECORD_KEY][f"page.{self.id()}"] = record.page_line(
                nonce="", state=record.TRANSPORT_STATE, cards="-/-", faulted=0, unreachable=0)
            raise RuntimeError(f"transport: {outcome} after {_APPLIED_ATTEMPTS} attempts")

        self.tc.extraresults[record.RECORD_KEY][f"page.{self.id()}"] = record.page_line(
            nonce=sample["nonce"], state=sample["state"], cards=sample["cards"],
            faulted=sample["faulted"], unreachable=sample["unreachable"])

        if outcome == "applied":
            return
        self.fail(outcome)
