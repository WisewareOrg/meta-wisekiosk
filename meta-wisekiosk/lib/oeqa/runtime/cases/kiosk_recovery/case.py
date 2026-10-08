import time

from framework import record
from framework.base import WiseKioskCase

from .verdict import read_sample, verdict as recovery_verdict

_DEADLINE_SECONDS = 30
_POLL_SECONDS = 2
_APPLIED_WAIT_SECONDS = 180
_BANNER_WAIT_SECONDS = 30


class KioskRecoveryTest(WiseKioskCase):

    # Self-sufficient, not OETestDepends-only: each test's own addCleanup
    # fires at that test's own tearDown, before the next test starts, so
    # this case stops the backend itself rather than relying on
    # kiosk_backend_unreachable's state surviving past that case's own
    # tearDown. docs/testing.md § "The render and applied cases" has why.

    def test_recovery(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(f"test_recovery requires role=bench, got {WiseKioskCase.role!r}")
        self.arm_probe()
        self.wait_applied(_APPLIED_WAIT_SECONDS)
        self.stop_backend()

        # The red half: the banner must be up (outage observed) before
        # starting the backend -- the record's page.<case id> line below
        # shows this alongside the after sample (review round-1 F2).
        before = None
        banner_by = time.time() + _BANNER_WAIT_SECONDS
        banner_start = time.time()
        while True:
            before = read_sample(self.titles())
            if before is not None and before["unreachable"] == 1:
                break
            if time.time() >= banner_by:
                raise RuntimeError(
                    f"stopping the backend did not reach the unreachable state within {_BANNER_WAIT_SECONDS}s")
            time.sleep(_POLL_SECONDS)
        before_seconds = round(time.time() - banner_start, 1)

        self.start_backend()
        start_time = time.time()
        deadline = start_time + _DEADLINE_SECONDS
        outcome, reason, after = "error", "no probe payload", None
        while True:
            after = read_sample(self.titles())
            outcome, reason = recovery_verdict(before, after)
            if outcome == "ok":
                break
            if time.time() >= deadline:
                break
            time.sleep(_POLL_SECONDS)

        if outcome == "ok":
            after_seconds = round(time.time() - start_time, 1)
            self.tc.extraresults[record.RECORD_KEY][f"page.{self.id()}"] = record.recovery_record_line(
                before_unreachable=before["unreachable"], before_loading=before["loading"],
                before_seconds=before_seconds, after_unreachable=after["unreachable"],
                after_loading=after["loading"], after_seconds=after_seconds)
            return
        self.fail(f"within {_DEADLINE_SECONDS}s of starting the backend: {reason}")
