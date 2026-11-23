"""Target suite: the board rejoins after a network outage."""

import time

from board.network.outage import Outage, OutageRecord
from board_test import BoardTest

_OUTAGE_SECONDS = 60
# TST029's bound
_REJOIN_BOUND_SECONDS = 30


class TestNetwork(BoardTest):
    """The board rejoins after a network outage."""

    def test_rejoins_after_an_outage(self) -> None:
        """TST029 rejoins after an outage: pin the board off its network, then time until a shell opens."""
        self.record(requirement="TST029")
        outage = self.board.network.outage
        outage.wait_boot_complete()
        boot_id = self.board.system.kernel.boot_id()

        outage.schedule(_OUTAGE_SECONDS)
        deadline = time.monotonic() + Outage.CUT_DELAY_SECONDS + _OUTAGE_SECONDS + Outage.GIVE_UP_SECONDS
        last_attempt = "no attempt"
        shells_before_cut = 0
        shells_during_outage = 0
        rejoined_s = None
        record = OutageRecord.from_lines([])
        while time.monotonic() < deadline:
            uptime_s, shell_record, last_attempt = outage.read_record_over_fresh_ssh()
            if shell_record is None:
                time.sleep(1)
                continue
            record = shell_record
            if record.cut is None or uptime_s < record.cut:
                shells_before_cut += 1
            elif record.restored is None:
                shells_during_outage += 1
                break
            else:
                # Board uptime at both ends; overstates by up to one poll plus one connect attempt.
                rejoined_s = round(uptime_s - record.restored, 1)
                break
            time.sleep(1)

        self.record(
            outage_s=_OUTAGE_SECONDS,
            cut_uptime_s=record.cut,
            t0_uptime_s=record.restored,
            rejoined_s=rejoined_s,
            shells_before_cut=shells_before_cut,
            shells_during_outage=shells_during_outage,
            last_attempt=last_attempt,
            trace=[line for line in record.lines if line.startswith("trace ")],
        )
        if rejoined_s is None and shells_during_outage == 0:
            self.record(journal_trace=outage.journal(boot_id))
        assert shells_during_outage == 0, "the network did not go away: a shell opened during the outage"
        assert rejoined_s is not None, f"no remote shell within {Outage.GIVE_UP_SECONDS} s of the network returning"
        assert rejoined_s <= _REJOIN_BOUND_SECONDS, (
            f"a shell opened {rejoined_s} s after the network returned; TST029's bound is {_REJOIN_BOUND_SECONDS} s"
        )
