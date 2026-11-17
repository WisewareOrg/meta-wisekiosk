"""Target suite: the appliance's memory use stays under its bound over a long run."""

import re
import subprocess
import time

import pytest
from labgrid.driver.exception import ExecutionError

from replay import CARDS4_LIVE

# TST014's period, and the period `--soak` gives it
PERIOD_SECONDS = 30 * 60
SOAK_PERIOD_SECONDS = 24 * 3600
# TST014's bound: use below this share of usable memory in every sample
USE_LIMIT = 0.80
# TST014's bound: growth in memory in use across a 30 minute window, in MB; picked, to be tuned from queue runs' windows
GROWTH_LIMIT_MB = 50
# kiosk-soak.sh's own gap rule, as its --summary applies it
MAX_GAP_SECONDS = 450
# how often the host checks the boot, so a reboot ends the run early
BOOT_CHECK_SECONDS = 600

_SOAK_LOG_PATH = "/data/kiosk-soak.log"
_OOM = re.compile(r"^\[\s*(\d+\.\d+)\].*(?:Out of memory|deadlocked on memory)")
_BOARD_ERRORS = (ExecutionError, subprocess.TimeoutExpired)


def _meminfo(board):
    """`/proc/meminfo` as a dict of kB."""
    stdout, _stderr, _returncode = board.run("cat /proc/meminfo", check=True)
    return {line.split(":")[0]: int(line.split()[1]) for line in stdout if ":" in line}


def _read_text(board, cmd):
    return "\n".join(board.run(cmd, check=True)[0]).strip()


def _soak_lines(board):
    """kiosk-soak's log lines as dicts of strings."""
    stdout, _stderr, _returncode = board.run(f"cat {_SOAK_LOG_PATH} 2>/dev/null; true")
    return [dict(token.split("=", 1) for token in line.split() if "=" in token) for line in stdout]


def _oom_uptimes(board, boot_flag, start, end):
    """Uptimes of out-of-memory kernel lines in `start`..`end` of the boot `boot_flag` names."""
    stdout, _stderr, returncode = board.run(
        f"journalctl -k {boot_flag} -o short-monotonic --no-pager"
    )
    found = [float(m.group(1)) for line in stdout if (m := _OOM.match(line))]
    return returncode, [up for up in found if start <= up <= end]


def _pstore_oom_uptimes(board, start, end):
    """Uptimes of out-of-memory lines in `start`..`end` of the previous boot's kernel console tail in pstore."""
    stdout, _stderr, returncode = board.run(
        'grep -q " /sys/fs/pstore " /proc/mounts || mount -t pstore pstore /sys/fs/pstore; '
        "cat /sys/fs/pstore/console-ramoops-0"
    )
    found = [float(m.group(1)) for line in stdout if (m := _OOM.match(line))]
    return returncode, [up for up in found if start <= up <= end]


def _boot_id(board):
    """The boot id and the reconnects made to read it; None if it could not be read, and a failed `reconnect()` raises."""
    cmd = "cat /proc/sys/kernel/random/boot_id"
    reconnects = 0
    try:
        return _read_text(board, cmd), reconnects
    except _BOARD_ERRORS:
        board.reconnect()
        reconnects = 1
    except AssertionError:
        return None, reconnects
    try:
        return _read_text(board, cmd), reconnects
    except (*_BOARD_ERRORS, AssertionError):
        return None, reconnects


def _wait_period(board, boot_id, period):
    """Sleep out `period` seconds, polling the boot; return the final boot id and reconnects made.

    Ends early on a changed boot id. The final read, made once more after the loop, leaves the
    session live for every read after it.
    """
    reconnects = 0
    end = time.monotonic() + period
    while time.monotonic() < end:
        time.sleep(min(BOOT_CHECK_SECONDS, max(0, end - time.monotonic())))
        now, made = _boot_id(board)
        reconnects += made
        if now is not None and now != boot_id:
            break
    final, made = _boot_id(board)
    reconnects += made
    assert final is not None, "the boot id could not be read after the period"
    return final, reconnects


@pytest.mark.parametrize("proxy", [str(CARDS4_LIVE / "flows.har")], indirect=True)
def test_memory_over_a_long_run(
    request, proxy, replay_window, panel, full_state, board, record_property
):
    """TST014 memory over a long run: kiosk-soak's samples of memory in use stay under `USE_LIMIT` of usable.

    Usable is `MemTotal`; in use is `MemTotal - MemAvailable`. A sample at or above the limit, or
    a process killed for memory, or growth in use over a valid 30 minute window beyond
    `GROWTH_LIMIT_MB` (not judged under `--soak`), fails; after a reset the kill is looked for in the previous
    boot's journal and in pstore's console record. A run is invalid, never a pass or a failure, if the boot
    changed without a memory kill, the browser or backend restarted, the page reloaded or
    changed state, kiosk-soak left a gap, or the replay killed a request.
    """
    record_property("requirement", "TST014")
    period = SOAK_PERIOD_SECONDS if request.config.getoption("--soak") else PERIOD_SECONDS
    record_property("period_s", period)
    timer_was_active = board.run("systemctl is-active kiosk-soak.timer")[2] == 0
    if not timer_was_active:
        request.addfinalizer(lambda: board.run("systemctl stop kiosk-soak.timer", check=True))
    board.run("systemctl start kiosk-soak.timer", check=True)
    record_property("timer_was_active", timer_was_active)

    boot_id = _read_text(board, "cat /proc/sys/kernel/random/boot_id")
    backend_pid = _read_text(board, "systemctl show -p MainPID --value wisekiosk.service")
    start_uptime = float(_read_text(board, "cat /proc/uptime").split()[0])
    start_mem = _meminfo(board)
    total_mb = start_mem["MemTotal"] / 1024
    start_sample = full_state[1]

    new_boot, reconnects = _wait_period(board, boot_id, period)
    record_property("reconnects", reconnects)
    rebooted = new_boot != boot_id

    problems = []
    failures = []
    if rebooted:
        returncode, oom = _oom_uptimes(board, "-b -1", start_uptime, float("inf"))
        console_returncode, console_oom = _pstore_oom_uptimes(board, start_uptime, float("inf"))
        oom = sorted({*oom, *console_oom})
        returncode = returncode or console_returncode
        if oom:
            failures.append(f"a process was killed for memory at uptime {oom[0]:.0f} s")
        else:
            problems.append(
                "the board rebooted, with no memory kill in the previous boot's kernel log or pstore console"
                if returncode == 0
                else "the board rebooted and the previous boot's kernel log or pstore console could not be read"
            )
        oom_count = len(oom)
        end_uptime = float("inf")
    else:
        end_uptime = float(_read_text(board, "cat /proc/uptime").split()[0])
        returncode, oom = _oom_uptimes(board, "-b", start_uptime, end_uptime)
        if returncode != 0:
            problems.append("the kernel log could not be read")
        oom_count = len(oom)
        if oom:
            failures.append(f"a process was killed for memory at uptime {oom[0]:.0f} s")

    lines = [
        line
        for line in _soak_lines(board)
        if line.get("boot") == boot_id[:8] and start_uptime <= float(line["up"]) <= end_uptime
    ]

    peak, peak_at = 0.0, None
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
        ups = [float(line["up"]) for line in lines]
        edges = [start_uptime, *ups, end_uptime]
        if not lines or max(b - a for a, b in zip(edges, edges[1:])) > MAX_GAP_SECONDS:
            problems.append(f"kiosk-soak left a gap over {MAX_GAP_SECONDS} s")
        if len({line["pid"] for line in lines}) > 1 or any(line["pid"] == "none" for line in lines):
            problems.append("the browser restarted or was not running at a sample")
        if _read_text(board, "systemctl show -p MainPID --value wisekiosk.service") != backend_pid:
            problems.append("wisekiosk.service restarted")
        try:
            _uptime, end_sample = panel.read()
        except _BOARD_ERRORS:
            end_sample = None
        if end_sample is None or any(
            end_sample[key] != start_sample[key] for key in ("load", "changes", "cards")
        ):
            problems.append("the page reloaded or changed state")
        if proxy.killed():
            problems.append(f"the replay killed requests: {proxy.killed()}")

    end_mem = _meminfo(board) if not rebooted else {}
    growth_mb = None
    if end_mem:
        growth_mb = (
            (end_mem["MemTotal"] - end_mem["MemAvailable"])
            - (start_mem["MemTotal"] - start_mem["MemAvailable"])
        ) / 1024
        record_property("growth_mb", round(growth_mb, 1))
        if not problems and not request.config.getoption("--soak") and growth_mb > GROWTH_LIMIT_MB:
            failures.append(
                f"memory in use grew {growth_mb:.0f} MB over the window; "
                f"TST014's bound is {GROWTH_LIMIT_MB} MB"
            )
    record_property("validity", "valid" if not problems else f"invalid: {'; '.join(problems)}")
    record_property("samples", len(lines))
    record_property("mem_total_mb", round(total_mb, 1))
    record_property("peak_use_pct", round(peak, 2))
    record_property("peak_at_uptime", peak_at)
    record_property("oom_lines", oom_count)
    record_property("swap_used_start_kb", start_mem["SwapTotal"] - start_mem["SwapFree"])
    if lines:
        record_property(
            "mem_use_delta_mb",
            float(lines[0]["memavail"]) - float(lines[-1]["memavail"]),
        )
        record_property("rss_total_delta_kb", int(lines[-1]["rss_total"]) - int(lines[0]["rss_total"]))
    if end_mem:
        record_property("swap_used_end_kb", end_mem["SwapTotal"] - end_mem["SwapFree"])

    assert not failures, "; ".join(failures)
    assert not problems, f"INVALID: {'; '.join(problems)}"
