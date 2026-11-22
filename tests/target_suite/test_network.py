"""Target suite: the board rejoins after a network outage, and holds the panel under network load."""

import time

from board.network.outage import Outage, OutageRecord
from board_test import BoardTest

_OUTAGE_SECONDS = 60
# TST029's bound
_REJOIN_BOUND_SECONDS = 30

# TST008's period
_LOAD_SECONDS = 60
# the least average rate that counts as the load applied, in MB/s
_LOAD_FLOOR_MB_S = 1.0
# TST008's allowance for a stop, and how long the panel is watched after the load ends
_STOP_ALLOWANCE_SECONDS = 60


class TestNetwork(BoardTest):
    """The board rejoins after a network outage, and holds the panel under network load."""

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

    def test_sustained_network_load(self) -> None:
        """TST008 sustained network load: push bytes at the board; no stop of the panel may exceed 60 s."""
        page = self.board.app.page
        self.record(probe_sha256=page.install_probe())
        self.record(requirement="TST008")
        page.wait_for_instance()
        load_start = self.board.run("true", check=True, with_uptime=True).uptime_s

        load = self.board.network.load.push(_LOAD_SECONDS)
        watch = page.watch(load_start)
        watch.read_while(load.is_running)
        load.wait()
        load_end = self.board.run("true", check=True, with_uptime=True).uptime_s
        watch.uptimes.append(load_end)
        observe_until = time.monotonic() + _STOP_ALLOWANCE_SECONDS
        watch.read_while(lambda: time.monotonic() < observe_until)

        longest_stop = watch.longest_stop_s(load_end, load_end + _STOP_ALLOWANCE_SECONDS)
        rate = load.sent / load.seconds / 1e6
        self.record(
            bytes=load.sent,
            seconds=round(load.seconds, 1),
            rate_mb_s=round(rate, 2),
            longest_stop_s=longest_stop,
            reads=watch.reads,
            off_panel_reads=watch.off_panel,
            failed_reads=watch.failed,
            nonces=sorted(watch.nonces),
        )
        assert load.returncode == 0 and load.received == str(load.sent), (
            f"the load was not applied: ssh returned {load.returncode}, sent {load.sent} B, "
            f"the board counted {load.received!r}"
        )
        assert load.seconds >= _LOAD_SECONDS and rate >= _LOAD_FLOOR_MB_S, (
            f"the load was not applied: {rate:.2f} MB/s over {load.seconds:.0f} s; "
            f"the floor is {_LOAD_FLOOR_MB_S} MB/s for {_LOAD_SECONDS} s"
        )
        assert watch.uptimes == sorted(watch.uptimes), "the board restarted during the test: its uptime went backwards"
        assert longest_stop <= _STOP_ALLOWANCE_SECONDS, (
            f"the panel was off for {longest_stop} s under load; TST008's allowance is {_STOP_ALLOWANCE_SECONDS} s"
        )
