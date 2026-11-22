"""The board's virtual terminals, and which one the panel shows."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from record import Record

    from board import Board

# the longest wait for X to take vt1 back after `kiosk.service` restarts
_KIOSK_RESTART_WAIT_SECONDS = 30


class Terminals:
    """The board's virtual terminals: the one in the foreground, X's on vt1, and tty2's login."""

    def __init__(self, board: "Board") -> None:
        """Bind to the board.

        Args:
            board: the board under test.
        """
        self._board = board

    def foreground_vt(self) -> str:
        """Read the virtual terminal in the foreground, as the board's `fgconsole` prints it.

        Returns:
            The terminal's number.
        """
        return self._board.run("fgconsole", check=True).stdout[0].strip()

    def bring_vt1_forward(self, when: str, record: "Record") -> None:
        """Make vt1 the foreground terminal, restarting `kiosk.service` (whose X takes vt1) if it is not.

        A restart is recorded as `console_restored_by_restart`, with `when` as its value.

        Args:
            when: `before` or `after`, as the restart is recorded.
            record: the test's record.
        """
        if self.foreground_vt() != "1":
            record(console_restored_by_restart=when)
            self._board.run("systemctl restart kiosk.service", check=True)
            self._board.poll(self.foreground_vt, until=lambda vt: vt == "1", within=_KIOSK_RESTART_WAIT_SECONDS)

    def x_server_on_vt1(self, when: str, record: "Record") -> None:
        """Record Xorg's pid and `kiosk.service`'s restart count, as `xorg_pid_<when>` and `kiosk_nrestarts_<when>`.

        Args:
            when: `before` or `after`, as the records are named.
            record: the test's record.
        """
        record(
            **{
                f"xorg_pid_{when}": " ".join(self._board.run("pidof Xorg").stdout),
                f"kiosk_nrestarts_{when}": self._board.run(
                    "systemctl show -p NRestarts --value kiosk.service", check=True
                ).stdout[0],
            }
        )

    def kill_tty2_login(self) -> None:
        """Kill whatever runs on tty2; `getty@.service`'s `Restart=always` brings back a fresh prompt.

        A logged-in shell outlasts a plain restart until systemd's stop timeout, so the unit is
        killed. It is not restarted: a getty that does not come back is left for the console wait to
        fail on.
        """
        self._board.run("systemctl kill -s KILL getty@tty2.service")

    def restore_after_test(self, record: "Record") -> None:
        """When the test ends, put vt1 back in the foreground with a fresh tty2 login, and record X after.

        Presses Ctrl+Alt+F1 on the board's keyboard, kills tty2's login, brings vt1 forward and
        records X's pid and restart count with `after`, then asserts vt1 is in the foreground.

        Args:
            record: the test's record.
        """
        self._board.cleanup.callback(self._restore, record)

    def _restore(self, record: "Record") -> None:
        """Put vt1 back in the foreground with a fresh tty2 login, and record X after.

        Args:
            record: the test's record.
        """
        self._board.console.keyboard.press_vt1_chord()
        self.kill_tty2_login()
        self.bring_vt1_forward("after", record)
        self.x_server_on_vt1("after", record)
        assert self.foreground_vt() == "1", "vt1 is not the foreground console after the test"
