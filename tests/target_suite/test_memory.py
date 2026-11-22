"""Target suite: the appliance's memory use stays under its bound over a long run."""

from typing import TYPE_CHECKING

import pytest
from board import Board
from board_test import BoardTest
from replay import CARDS4_LIVE

if TYPE_CHECKING:
    from wisebench.proxy import Proxy

# TST014's period, and the period `--soak` gives it
PERIOD_SECONDS = 30 * 60
SOAK_PERIOD_SECONDS = 24 * 3600
# TST014's bound: use below this share of usable memory in every sample
USE_LIMIT = 0.80
# TST014's bound on growth in memory in use across the window, in MB
GROWTH_LIMIT_MB = 100


class TestMemory(BoardTest):
    """The appliance's memory use stays under its bound over a long run."""

    @pytest.mark.parametrize("proxy", [str(CARDS4_LIVE / "flows.har")], indirect=True)
    def test_memory_over_a_long_run(self, proxy: "Proxy", pytestconfig: pytest.Config) -> None:
        """TST014 memory over a long run: kiosk-soak's samples of memory in use stay under `USE_LIMIT` of usable.

        Usable is `MemTotal`; in use is `MemTotal - MemAvailable`. A sample at or above the limit, or
        a process killed for memory, or growth in use over a valid 30 minute window beyond
        `GROWTH_LIMIT_MB` (not judged under `--soak`), fails; after a reset the kill is looked for in the
        previous boot's journal and in pstore's console record. A run is invalid, never a pass or a
        failure, if the boot changed without a memory kill, the browser or backend restarted, the page
        reloaded or changed state, kiosk-soak left a gap, the replay killed a request, or the evidence
        is unreadable.

        Args:
            proxy: the proxy replaying the cards4-live recording.
            pytestconfig: the run's config, which says whether `--soak` was given.

        Raises:
            AssertionError: the failures found so far, when reading the evidence then broke unexpectedly.
            Exception: what broke the evidence's reading, when no failure had been found.
        """
        page = self.board.app.page
        memory = self.board.system.memory
        soak = self.board.system.soak
        self.board.app.backend.put_behind(proxy, CARDS4_LIVE / "config.json")
        self.record(probe_sha256=page.install_probe())
        _, start_sample = page.wait_for_instance(all_cards_live=True)
        self.record(requirement="TST014")
        soak_run = pytestconfig.getoption("--soak")
        period = SOAK_PERIOD_SECONDS if soak_run else PERIOD_SECONDS
        self.record(period_s=period)
        self.record(timer_was_active=soak.start_sampler())
        boot_id = self.board.run(Board.BOOT_ID_CMD, check=True, retry_for=Board.READ_RETRY_SECONDS).text
        backend_pid = self.board.app.backend.pid(retry_for=Board.READ_RETRY_SECONDS)
        start_uptime = float(
            self.board.run("cat /proc/uptime", check=True, retry_for=Board.READ_RETRY_SECONDS).text.split()[0]
        )
        start_mem = memory.meminfo_kb()
        total_mb = start_mem["MemTotal"] / 1024

        new_boot = self.board.sleep_watching_boot(boot_id, period)
        if new_boot is None:
            reason = "evidence unreadable: the boot id could not be read after the period"
            self.record(validity=f"invalid: {reason}")
            pytest.fail(f"INVALID: {reason}")
        rebooted = new_boot != boot_id

        problems = []
        failures = []
        lines, peak, peak_at, oom_count, end_mem = [], 0.0, None, 0, {}
        try:
            if rebooted:
                journal_kills = memory.oom_kills_previous_boot(start_uptime)
                console_kills = memory.oom_kills_in_pstore(start_uptime)
                oom = sorted({*journal_kills.uptimes, *console_kills.uptimes})
                returncode = journal_kills.returncode or console_kills.returncode
                if oom:
                    failures.append(f"a process was killed for memory at uptime {oom[0]:.0f} s")
                else:
                    problems.append(
                        "the board rebooted, with no memory kill in the previous boot's kernel log or pstore console"
                        if returncode == 0
                        else "the board rebooted and the previous boot's kernel log or pstore console could not be read"
                    )
                oom_count = len(oom)
            else:
                kills = memory.oom_kills_this_boot(start_uptime)
                if kills.returncode != 0:
                    problems.append("the kernel log could not be read")
                oom_count = len(kills.uptimes)
                if kills.uptimes:
                    failures.append(f"a process was killed for memory at uptime {kills.uptimes[0]:.0f} s")
        except Board.ERRORS as exc:
            problems.append(f"evidence unreadable: {type(exc).__name__}")

        try:
            end_uptime = (
                float("inf")
                if rebooted
                else float(
                    self.board.run("cat /proc/uptime", check=True, retry_for=Board.READ_RETRY_SECONDS).text.split()[0]
                )
            )
            lines = soak.samples(boot_id, start_uptime, end_uptime, period)

            if any(not 0 <= float(line["memavail"]) <= total_mb for line in lines):
                problems.append("evidence unreadable: kiosk-soak's memavail is not in MB of usable memory")
            for line in lines:
                use = 100 * (total_mb - float(line["memavail"])) / total_mb
                if use > peak:
                    peak, peak_at = use, float(line["up"])
            if peak >= USE_LIMIT * 100:
                failures.insert(
                    0,
                    f"memory in use reached {peak:.1f}% of usable at uptime {peak_at:.0f} s; "
                    f"TST014's bound is {USE_LIMIT:.0%}",
                )

            if not rebooted:
                if soak.left_a_gap(lines, start_uptime, end_uptime):
                    problems.append(f"kiosk-soak left a gap over {soak.MAX_GAP_SECONDS} s")
                if len({line["pid"] for line in lines}) > 1 or any(line["pid"] == "none" for line in lines):
                    problems.append("the browser restarted or was not running at a sample")
                if self.board.app.backend.pid(retry_for=Board.READ_RETRY_SECONDS) != backend_pid:
                    problems.append("wisekiosk.service restarted")
                try:
                    end_sample = page.read().sample
                except (*Board.ERRORS, IndexError):
                    end_sample = None
                if end_sample is None:
                    problems.append("the end page read failed")
                elif any(end_sample[key] != start_sample[key] for key in ("load", "changes", "cards")):
                    problems.append("the page reloaded or changed state")
                if proxy.killed():
                    problems.append(f"the replay killed requests: {proxy.killed()}")

            end_mem = memory.meminfo_kb() if not rebooted else {}
            if end_mem:
                growth_mb = (
                    (end_mem["MemTotal"] - end_mem["MemAvailable"])
                    - (start_mem["MemTotal"] - start_mem["MemAvailable"])
                ) / 1024
                self.record(growth_mb=round(growth_mb, 1))
                if not problems and not soak_run and growth_mb > GROWTH_LIMIT_MB:
                    failures.append(
                        f"memory in use grew {growth_mb:.0f} MB over the window; TST014's bound is {GROWTH_LIMIT_MB} MB"
                    )
        except Board.ERRORS as exc:
            problems.append(f"evidence unreadable: {type(exc).__name__}")
        except Exception as exc:
            if failures:
                raise AssertionError("; ".join(failures)) from exc
            raise
        self.record(
            validity="valid" if not problems else f"invalid: {'; '.join(problems)}",
            samples=len(lines),
            mem_total_mb=round(total_mb, 1),
            peak_use_pct=round(peak, 2),
            peak_at_uptime=peak_at,
            oom_lines=oom_count,
            swap_used_start_kb=start_mem["SwapTotal"] - start_mem["SwapFree"],
        )
        if lines:
            self.record(rss_total_delta_kb=int(lines[-1]["rss_total"]) - int(lines[0]["rss_total"]))
        if end_mem:
            self.record(swap_used_end_kb=end_mem["SwapTotal"] - end_mem["SwapFree"])

        assert not failures, "; ".join(failures)
        assert not problems, f"INVALID: {'; '.join(problems)}"
