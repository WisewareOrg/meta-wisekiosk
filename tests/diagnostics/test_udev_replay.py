"""Diagnostics: what udevd's CPU goes on, per subsystem, by replaying the boot's add events.

For each subsystem the board has devices in, over three passes, it reads the CPU time of udevd and
of PID 1, replays that subsystem's `add` events with `udevadm trigger --type=all`, waits for
`udevadm settle`, and reads both again. A subsystem no device is in (`kiosk-no-such-subsystem`)
goes first in every pass as the zero control. `net` is never replayed: it is the session's own link.

It records figures and gives no verdict on them. It fails only when the measurement is void: the
control costs udevd more than `CONTROL_LIMIT_US` in a pass, the boot id or the loaded module names
differ before and after, or the browser restarted between passes. The replay is a lower bound on
boot cost: it meets no cold cache and loads no module. The board is restarted at the end.

Outside the regression suite: run through the bench driver, the form is in docs/testing.md.
"""

from collections.abc import Callable

from board import Board

PASSES = 3
CONTROL = "kiosk-no-such-subsystem"
CONTROL_LIMIT_US = 100_000

_NOT_REPLAYED = "net"  # counted with a dry run, which sends no event
# Neither is under /sys/class or /sys/bus, and the boot's own trigger covers both.
_OUTSIDE_CLASS_AND_BUS = ("module", "subsystem", "drivers")
_UDEVD_STAT = "/sys/fs/cgroup/system.slice/systemd-udevd.service/cpu.stat"
_PID1_STAT = "/sys/fs/cgroup/init.scope/cpu.stat"


def _subsystems(board: Board) -> list[str]:
    """List the subsystems to replay.

    Args:
        board: the board under test.

    Returns:
        The names under /sys/class and /sys/bus, and the three outside both, less `net`, sorted.
    """
    names = set(board.run("ls -1 /sys/class; ls -1 /sys/bus", check=True).stdout)
    names.update(_OUTSIDE_CLASS_AND_BUS)
    names.discard(_NOT_REPLAYED)
    return sorted(name.strip() for name in names if name.strip())


def _device_count(board: Board, name: str) -> int:
    """Count the devices a replay of `name` would send an event for, sending none.

    Args:
        board: the board under test.
        name: the subsystem.

    Returns:
        The number of lines `udevadm trigger --dry-run --verbose` prints.
    """
    return len(board.run(f"udevadm trigger --dry-run --verbose --type=all --subsystem-match={name}", check=True).stdout)


def _replay(board: Board, name: str) -> tuple[int, int]:
    """Replay `name`'s add events and read what they cost, in one command.

    Args:
        board: the board under test.
        name: the subsystem.

    Returns:
        The microseconds of CPU udevd and PID 1 used between the two reads.
    """
    stat = "sed -n 's/^usage_usec //p'"
    script = (
        f"u0=$({stat} {_UDEVD_STAT}) && p0=$({stat} {_PID1_STAT}) && "
        f"udevadm trigger --type=all --action=add --subsystem-match={name} && udevadm settle && "
        f"u1=$({stat} {_UDEVD_STAT}) && p1=$({stat} {_PID1_STAT}) && "
        'echo "$((u1 - u0)) $((p1 - p0))"'
    )
    udevd_us, pid1_us = board.run(script, timeout=None, check=True).text.split()
    return int(udevd_us), int(pid1_us)


def _module_names(board: Board) -> list[str]:
    """List the loaded kernel modules by name.

    Args:
        board: the board under test.

    Returns:
        The names, sorted.
    """
    return board.run("awk '{print $1}' /proc/modules | sort", check=True).stdout


def _browser_invocation(board: Board) -> str:
    """Read the id of the browser unit's current run, which a restart changes.

    Args:
        board: the board under test.

    Returns:
        The invocation id.
    """
    return board.run("systemctl show -p InvocationID --value kiosk.service", check=True).text


def test_udev_replay(board: Board, record_property: Callable[[str, object], None]) -> None:
    """Replay each subsystem's add events three times and record what they cost udevd and PID 1.

    Args:
        board: the board under test.
        record_property: records the device counts and the figures.
    """
    boot_id = board.boot_id()
    modules = _module_names(board)
    invocation = _browser_invocation(board)

    everything = board.run("udevadm trigger --dry-run --verbose --type=all", check=True).stdout
    record_property("devices_all", len(everything))
    record_property("dry_run_all", "\n".join(everything))

    counts = {name: _device_count(board, name) for name in _subsystems(board)}
    for name, count in counts.items():
        record_property(f"devices.{name}", count)
    net_count = _device_count(board, _NOT_REPLAYED)
    record_property(f"devices.{_NOT_REPLAYED}", net_count)
    record_property("devices_sum_with_net", sum(counts.values()) + net_count)
    replayed = [name for name, count in counts.items() if count > 0]
    record_property("skipped_no_devices", " ".join(name for name, count in counts.items() if count == 0))

    try:
        for number in range(1, PASSES + 1):
            control_us, control_pid1_us = _replay(board, CONTROL)
            record_property(f"pass{number}.{CONTROL}.udevd_us", control_us)
            record_property(f"pass{number}.{CONTROL}.pid1_us", control_pid1_us)
            assert control_us <= CONTROL_LIMIT_US, (
                f"pass {number}: the zero control cost udevd {control_us} us, above {CONTROL_LIMIT_US}: void"
            )
            for name in replayed:
                udevd_us, pid1_us = _replay(board, name)
                record_property(f"pass{number}.{name}.udevd_us", udevd_us)
                record_property(f"pass{number}.{name}.pid1_us", pid1_us)
            assert _browser_invocation(board) == invocation, f"pass {number}: the browser restarted: void"
        assert board.boot_id() == boot_id, "the board rebooted during the replay: void"
        assert _module_names(board) == modules, "the loaded modules changed during the replay: void"
    finally:
        board.restart()
