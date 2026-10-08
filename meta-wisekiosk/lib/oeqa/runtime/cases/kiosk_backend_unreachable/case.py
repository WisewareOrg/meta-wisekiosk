import time

from framework import record
from framework.base import WiseKioskCase

from .verdict import read_sample, verdict as unreachable_verdict

_DEADLINE_SECONDS = 30
_POLL_SECONDS = 2
_APPLIED_WAIT_SECONDS = 180


class KioskBackendUnreachableTest(WiseKioskCase):

    def test_backend_unreachable(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_backend_unreachable requires role=bench, got {WiseKioskCase.role!r}")
        self.arm_probe()

        # The red half: the page applied (unreachable=0) before the
        # backend is stopped -- the record's page.<case id> line below
        # shows this alongside the after sample (review round-1 F2).
        before_start = time.time()
        self.wait_applied(_APPLIED_WAIT_SECONDS)
        before_seconds = round(time.time() - before_start, 1)
        before = read_sample(self.titles()) or {}

        self.stop_backend()
        stop_start = time.time()

        deadline = stop_start + _DEADLINE_SECONDS
        outcome, reason, after = "error", "no probe payload", None
        while True:
            after = read_sample(self.titles())
            outcome, reason = unreachable_verdict(after)
            if outcome == "ok":
                break
            if time.time() >= deadline:
                break
            time.sleep(_POLL_SECONDS)

        if outcome == "ok":
            after_seconds = round(time.time() - stop_start, 1)
            self.tc.extraresults[record.RECORD_KEY][f"page.{self.id()}"] = record.unreachable_record_line(
                before_unreachable=before.get("unreachable", "?"), before_seconds=before_seconds,
                after_unreachable=after["unreachable"], after_seconds=after_seconds)
            return
        self.fail(f"within {_DEADLINE_SECONDS}s of stopping the backend: {reason}")
