"""A systemd unit on the board."""

import contextlib
import time
from typing import TYPE_CHECKING

from board.part import Part

if TYPE_CHECKING:
    from board import Board

# covers a daemon-reload plus a unit start
RELOAD_TIMEOUT_SECONDS = 60


class Unit(Part):
    """A systemd unit on the board.

    Attributes:
        name: the unit's name.
    """

    name: str

    def __init__(self, board: "Board", name: str) -> None:
        """Bind to the board and name the unit.

        Args:
            board: the board under test.
            name: the unit's name.
        """
        super().__init__(board)
        self.name = name

    def kill(self) -> float:
        """Kill every process of the unit outright, with SIGKILL.

        Returns:
            The host `time.monotonic()` just before the kill.
        """
        sent = time.monotonic()
        self._board.run(f"systemctl kill --signal=KILL {self.name}", check=True)
        return sent

    def restart(self) -> None:
        """Restart the unit."""
        self._board.run(f"systemctl restart {self.name}", check=True)

    def is_active(self) -> bool:
        """Whether the unit is active.

        Returns:
            True if systemd says so.
        """
        return self._board.run(f"systemctl is-active {self.name}").returncode == 0

    def mask(self) -> None:
        """Mask the unit for this boot only, so nothing starts it; when the test ends it is unmasked and started."""
        self._board.cleanup.callback(self.unmask)
        self._board.run(f"systemctl mask --runtime {self.name}", check=True)

    def unmask(self) -> None:
        """Unmask a unit masked for this boot, and start it."""
        self._board.run(self._unmask, check=True)

    def unmask_later(self, delay: float) -> None:
        """Have the board unmask and start the unit in `delay` seconds by itself, until the test ends.

        Args:
            delay: seconds from now.
        """
        self._board.run_later(f"test-unmask-{self.name.split('.')[0]}", delay, f"/bin/sh -c '{self._unmask}'")

    @property
    def _drop_in_dir(self) -> str:
        """The directory of the unit's runtime drop-ins.

        Returns:
            The path.
        """
        return f"/run/systemd/system/{self.name}.d"

    @property
    def _drop_in(self) -> str:
        """The runtime drop-in the tests write.

        Returns:
            The path.
        """
        return f"{self._drop_in_dir}/test.conf"

    @property
    def _unmask(self) -> str:
        """The command that unmasks the unit for this boot and starts it.

        Returns:
            The command.
        """
        return f"systemctl unmask --runtime {self.name}; systemctl start {self.name}"

    def drop_in(self, text: str, cleanup: contextlib.ExitStack | None = None) -> None:
        """Add `text` to the unit as a runtime drop-in; when it is undone, the unit is started.

        Args:
            text: the drop-in's contents, as `printf` takes them.
            cleanup: where the undo is registered: the board's cleanup, for the end of the test, when None.
        """
        (cleanup if cleanup is not None else self._board.cleanup).callback(
            self._board.run,
            f"rm -f {self._drop_in}; systemctl daemon-reload; systemctl start {self.name}",
            check=True,
            timeout=RELOAD_TIMEOUT_SECONDS,
        )
        self._board.run(
            f"mkdir -p {self._drop_in_dir} && printf '{text}' > {self._drop_in} && systemctl daemon-reload",
            check=True,
            timeout=RELOAD_TIMEOUT_SECONDS,
        )

    def clear_runtime_changes(self) -> None:
        """Remove the runtime drop-ins and the runtime mask a dead run left on the unit, and start it."""
        self._board.run(
            f'if [ -d {self._drop_in_dir} ] || [ "$(systemctl is-enabled {self.name})" = masked-runtime ]; then '
            f"rm -rf {self._drop_in_dir}; systemctl unmask --runtime {self.name}; "
            f"systemctl daemon-reload; systemctl start {self.name}; fi",
            check=True,
            timeout=RELOAD_TIMEOUT_SECONDS,
        )

    def main_pid(self, retry_for: float | None = None) -> str:
        """Read the unit's main process id, as systemd reports it.

        Args:
            retry_for: how long to retry through a dropped session, as `Board.run` takes it; None reads once.

        Returns:
            The pid.
        """
        return self._board.run(f"systemctl show -p MainPID --value {self.name}", check=True, retry_for=retry_for).text
