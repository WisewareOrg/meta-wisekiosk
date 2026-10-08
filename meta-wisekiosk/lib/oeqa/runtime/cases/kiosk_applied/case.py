import time
from pathlib import Path

from framework import record
from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS, POLL_SECONDS

from .verdict import read_sample, verdict as applied_verdict

PROBE_SRC = Path(__file__).resolve().parent / "probe.js"

APPLIED_WAIT_SECONDS = 90
_APPLIED_ATTEMPTS = 2


def deploy_probe(case):
    """Deploys this package's probe.js (mkdir, copyTo) and registers its
    own removal as the case's cleanup."""
    case.addCleanup(case.target.run, "rm -f /home/root/.surf/script.js")
    mkdir_status, _ = case.target.run(
        "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
    if mkdir_status != 0:
        raise RuntimeError("could not deploy the probe (mkdir)")
    case.target.copyTo(str(PROBE_SRC), "/home/root/.surf/script.js")


def wait_applied(case, deadline_s):
    """Polls case.titles() until some window's probe payload reads
    state=applied, raising with the last known state if deadline_s
    elapses first."""
    deadline = time.monotonic() + deadline_s
    last = "no probe payload"
    while True:
        sample = read_sample(case.titles())
        if sample is not None:
            last = sample["state"]
            if last == "applied":
                return
        if time.monotonic() >= deadline:
            break
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"the page did not apply within {deadline_s}s (last: {last})")


def applied_attempt(case):
    # A deploy failure here takes the same retry path as a probe
    # failure: the caller only ever sees an "error" outcome. Deploy
    # (mkdir, copyTo) runs before the clock and is unbounded; the 90 s
    # deadline starts when the restart is issued -- the restart's own
    # duration counts, and the poll gets the remainder.
    try:
        deploy_probe(case)
        deadline = time.monotonic() + APPLIED_WAIT_SECONDS
        restart_status, _ = case.target.run(
            "systemctl restart kiosk.service", timeout=int(max(1, deadline - time.monotonic())))
        if restart_status != 0:
            return "error", "deploy", None
    except AssertionError:
        return "error", "deploy", None

    samples = []
    while True:
        samples.append(read_sample(case.titles()))
        outcome, reason = applied_verdict(samples)
        if outcome == "applied":
            return outcome, reason, samples[-1]
        if time.monotonic() >= deadline:
            break
        time.sleep(POLL_SECONDS)

    outcome, reason = applied_verdict(samples)
    real = [sample for sample in samples if sample is not None]
    return outcome, reason, (real[-1] if real else None)


class KioskAppliedTest(WiseKioskCase):

    def test_page_applied(self):
        outcome, reason, sample = None, None, None
        for _attempt in range(_APPLIED_ATTEMPTS):
            outcome, reason, sample = applied_attempt(self)
            if outcome != "error":
                break
        else:
            # The declared transport kind: run.sh's own infrastructure-
            # failure path reads this exact state from the page line.
            self.tc.extraresults[record.RECORD_KEY][f"page.{self.id()}"] = record.page_line(
                nonce="", state=record.TRANSPORT_STATE, cards="-/-", faulted=0, unreachable=0)
            raise RuntimeError(f"transport: {outcome}:{reason} after {_APPLIED_ATTEMPTS} attempts")

        self.tc.extraresults[record.RECORD_KEY][f"page.{self.id()}"] = record.page_line(
            nonce=sample["nonce"], state=sample["state"], cards=sample["cards"],
            faulted=sample["faulted"], unreachable=sample["unreachable"])

        if outcome == "applied":
            return
        self.fail(f"{outcome}:{reason}")
