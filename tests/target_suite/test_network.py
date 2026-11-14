"""Target suite: the board rejoins after a network outage, and holds the panel under network load."""

import os
import subprocess
import threading
import time
from pathlib import Path

from labgrid.driver.exception import ExecutionError

_OUTAGE_SRC = Path(__file__).resolve().parent / "outage.sh"
_OUTAGE_SCRIPT_PATH = "/tmp/test-outage.sh"
_OUTAGE_RECORD_PATH = "/tmp/test-outage.record"
_OUTAGE_UNIT = "test-outage"
# the delay `systemd-run` waits before the script cuts, so the arming command returns first
_ARM_DELAY_SECONDS = 3
_OUTAGE_SECONDS = 60
# stop polling this long after the network returns; past the bound, so the record carries the time
_GIVE_UP_SECONDS = 180
# TST029's bound
_REJOIN_BOUND_SECONDS = 30
_BOOT_COMPLETE_WAIT_SECONDS = 180
_SHELL_TIMEOUT_SECONDS = 10

_BLOCK_BYTES = 1024 * 1024
_LOAD_SECONDS = 60
# the least average rate that counts as the load applied, in MB/s
_LOAD_FLOOR_MB_S = 1.0
# TST008's allowance for a stop, and how long the panel is watched after the load ends
_STOP_ALLOWANCE_SECONDS = 60
# how long past the load the push may run before it is killed as hung
_PUSH_GRACE_SECONDS = 60
_READ_PAUSE_SECONDS = 1


def _record_lines(board):
    """The outage record's lines as the board holds them (empty if absent), on the SSHDriver."""
    return board.run(f"cat {_OUTAGE_RECORD_PATH} 2>/dev/null || true", check=True)[0]


def _wait_boot_complete(board):
    """Wait for boot-complete.target, so an outage cannot land inside kiosk-netcheck's window."""
    deadline = time.monotonic() + _BOOT_COMPLETE_WAIT_SECONDS
    while board.run("systemctl is-active boot-complete.target")[2] != 0:
        assert time.monotonic() < deadline, (
            f"boot-complete.target was not active within {_BOOT_COMPLETE_WAIT_SECONDS} s"
        )
        time.sleep(1)


def _arm_outage(request, board):
    """Copy the outage script to the board and start it on a timer; undo each step at teardown.

    The SSHDriver is disconnected last, while the board is still up. Teardown reconnects it,
    stops the units, un-pins the network the record names, then removes the files.
    """
    board.put(str(_OUTAGE_SRC), _OUTAGE_SCRIPT_PATH)
    request.addfinalizer(lambda: board.run(f"rm -f {_OUTAGE_SCRIPT_PATH} {_OUTAGE_RECORD_PATH}"))

    def unpin():
        for line in _record_lines(board):
            fields = line.split()
            if fields[:1] == ["id"] and len(fields) == 2:
                board.run(f"wpa_cli -i wlan0 set_network {fields[1]} bssid any")
                return

    request.addfinalizer(unpin)

    board.run(
        f"systemd-run --unit={_OUTAGE_UNIT} --on-active={_ARM_DELAY_SECONDS} "
        f"--timer-property=AccuracySec=100ms /bin/sh {_OUTAGE_SCRIPT_PATH} "
        f"{_OUTAGE_SECONDS} {_GIVE_UP_SECONDS}",
        check=True,
    )
    units = f"{_OUTAGE_UNIT}.timer {_OUTAGE_UNIT}.service"
    request.addfinalizer(
        lambda: board.run(f"systemctl stop {units}; systemctl reset-failed {units}")
    )

    request.addfinalizer(board.reconnect)
    board.disconnect()


def _shell(board):
    """Open a new ssh shell; return its (uptime, record lines) or None, and how the attempt ended."""
    try:
        done = subprocess.run(
            [
                *board.fresh_ssh_argv("ConnectTimeout=5"),
                f"cat /proc/uptime; cat {_OUTAGE_RECORD_PATH} 2>/dev/null; true",
            ],
            capture_output=True,
            text=True,
            timeout=_SHELL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, f"timed out after {_SHELL_TIMEOUT_SECONDS} s"
    if done.returncode != 0:
        return None, f"rc {done.returncode}, stderr {done.stderr.strip()[-200:]!r}"
    lines = done.stdout.splitlines()
    return (float(lines[0].split()[0]), lines[1:]), "opened"


def _field(lines, name):
    """The number after the first `name` line of the record, else None."""
    for line in lines:
        fields = line.split()
        if fields[:1] == [name]:
            return float(fields[1])
    return None


def test_rejoins_after_an_outage(request, board, record_property):
    """TST029 rejoins after an outage: pin the board off its network, then time until a shell opens."""
    record_property("requirement", "TST029")
    _wait_boot_complete(board)
    _arm_outage(request, board)
    deadline = time.monotonic() + _ARM_DELAY_SECONDS + _OUTAGE_SECONDS + _GIVE_UP_SECONDS

    last_attempt = "no attempt"
    shells_before_cut = 0
    shells_during_outage = 0
    rejoined_s = None
    cut_at = t0 = None
    lines = []
    while time.monotonic() < deadline:
        opened, last_attempt = _shell(board)
        if opened is None:
            time.sleep(1)
            continue
        t1, lines = opened
        cut_at = _field(lines, "cut")
        t0 = _field(lines, "t0")
        if cut_at is None or t1 < cut_at:
            shells_before_cut += 1
        elif t0 is None:
            shells_during_outage += 1
            break
        else:
            # Board uptime at both ends; overstates by up to one poll plus one connect attempt.
            rejoined_s = round(t1 - t0, 1)
            break
        time.sleep(1)

    record_property("outage_s", _OUTAGE_SECONDS)
    record_property("cut_uptime_s", cut_at)
    record_property("t0_uptime_s", t0)
    record_property("rejoined_s", rejoined_s)
    record_property("shells_before_cut", shells_before_cut)
    record_property("shells_during_outage", shells_during_outage)
    record_property("last_attempt", last_attempt)
    record_property("trace", [line for line in lines if line.startswith("trace ")])

    if rejoined_s is None:
        board.reconnect()
        journal = board.run(f"journalctl -b -1 -u {_OUTAGE_UNIT} -o cat --no-pager")[0]
        record_property("journal_trace", journal)

    assert shells_during_outage == 0, "the network did not go away: a shell opened during the outage"
    assert rejoined_s is not None, f"no remote shell within {_GIVE_UP_SECONDS} s of the network returning"
    assert rejoined_s >= 0, f"the board restarted during the test: t1 - t0 was {rejoined_s} s"
    assert rejoined_s <= _REJOIN_BOUND_SECONDS, (
        f"a shell opened {rejoined_s} s after the network returned; "
        f"TST029's bound is {_REJOIN_BOUND_SECONDS} s"
    )


def _push(proc, result):
    """Write random blocks to `proc` for `_LOAD_SECONDS`, close it, and record how it ended."""
    sent = 0
    started = time.monotonic()
    end = started + _LOAD_SECONDS
    try:
        while time.monotonic() < end:
            proc.stdin.write(os.urandom(_BLOCK_BYTES))
            sent += _BLOCK_BYTES
        proc.stdin.close()
        received = proc.stdout.read().decode(errors="replace").strip()
    except OSError:  # the ssh died or was killed
        received = ""
    result["returncode"] = proc.wait()
    result["seconds"] = time.monotonic() - started
    result["sent"] = sent
    result["received"] = received


def _watch(panel, seen, keep_going):
    """Read the panel once a second while `keep_going()`, tallying each read into `seen`."""
    while keep_going():
        seen["reads"] += 1
        try:
            uptime_s, sample = panel.read()
        except (ExecutionError, subprocess.TimeoutExpired):
            seen["failed"] += 1
            seen["off_panel"] += 1
        else:
            seen["uptimes"].append(uptime_s)
            if sample is None:
                seen["failed"] += 1
            if panel.on_panel(sample):
                seen["on_panel_at"].append(uptime_s)
                seen["nonces"].add(sample["nonce"])
            else:
                seen["off_panel"] += 1
        time.sleep(_READ_PAUSE_SECONDS)


def test_sustained_network_load(request, board, panel, record_property):
    """TST008 sustained network load: push bytes at the board; no stop of the panel may exceed 60 s."""
    record_property("requirement", "TST008")
    panel.wait_on_panel()
    load_start = float(board.run("cat /proc/uptime", check=True)[0][0].split()[0])

    proc = subprocess.Popen(
        [
            *board.fresh_ssh_argv(
                "ConnectTimeout=10", "ServerAliveInterval=15", "ServerAliveCountMax=4"
            ),
            "wc -c",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    request.addfinalizer(proc.wait)
    request.addfinalizer(proc.kill)
    result = {}
    pusher = threading.Thread(target=_push, args=(proc, result))
    push_deadline = time.monotonic() + _LOAD_SECONDS + _PUSH_GRACE_SECONDS
    pusher.start()

    seen = {
        "reads": 0,
        "failed": 0,
        "off_panel": 0,
        "uptimes": [load_start],
        "on_panel_at": [load_start],
        "nonces": set(),
    }

    def pushing():
        if time.monotonic() > push_deadline:
            proc.kill()
        return pusher.is_alive()

    _watch(panel, seen, pushing)
    pusher.join()
    load_end = float(board.run("cat /proc/uptime", check=True)[0][0].split()[0])
    seen["uptimes"].append(load_end)
    observe_until = time.monotonic() + _STOP_ALLOWANCE_SECONDS
    _watch(panel, seen, lambda: time.monotonic() < observe_until)

    observation_end = load_end + _STOP_ALLOWANCE_SECONDS
    on_panel_at = seen["on_panel_at"]
    # An interval runs from an on-panel read to the next; the last runs to the end of observation.
    starts = [at for at in on_panel_at if at <= load_end]
    ends = on_panel_at[1:] + [observation_end]
    longest_stop = round(max(end - start for start, end in zip(starts, ends)), 1)
    rate = result["sent"] / result["seconds"] / 1e6
    record_property("bytes", result["sent"])
    record_property("seconds", round(result["seconds"], 1))
    record_property("rate_mb_s", round(rate, 2))
    record_property("longest_stop_s", longest_stop)
    record_property("reads", seen["reads"])
    record_property("off_panel_reads", seen["off_panel"])
    record_property("failed_reads", seen["failed"])
    record_property("nonces", sorted(seen["nonces"]))

    assert result["returncode"] == 0 and result["received"] == str(result["sent"]), (
        f"the load was not applied: ssh returned {result['returncode']}, sent {result['sent']} B, "
        f"the board counted {result['received']!r}"
    )
    assert result["seconds"] >= _LOAD_SECONDS and rate >= _LOAD_FLOOR_MB_S, (
        f"the load was not applied: {rate:.2f} MB/s over {result['seconds']:.0f} s; "
        f"the floor is {_LOAD_FLOOR_MB_S} MB/s for {_LOAD_SECONDS} s"
    )
    assert seen["uptimes"] == sorted(seen["uptimes"]), (
        "the board restarted during the test: its uptime went backwards"
    )
    assert longest_stop <= _STOP_ALLOWANCE_SECONDS, (
        f"the panel was off for {longest_stop} s under load; TST008's allowance is "
        f"{_STOP_ALLOWANCE_SECONDS} s"
    )
