"""Offering an image update to the board through the one install path."""

import contextlib
import json
import os
import pathlib
import signal
import subprocess
import time
from collections.abc import Callable

from board import Board

_INSTALL_TOOL = pathlib.Path(__file__).resolve().parents[2] / "tools" / "kiosk-install.sh"
# how long the tool may take to clean up after a SIGTERM
_CLEANUP_SECONDS = 120


class Update:
    """Image updates offered to the board through `tools/kiosk-install.sh`, the board's one install path.

    The test must carry the `sends_update` marker, which orders it after every test that does not;
    the fixture that builds the update asserts that.
    A `record_property` makes `refuse` record the refused offer; the image-update tests pass none,
    because they record their accepted install under the same names.
    """

    def __init__(
        self,
        board: Board,
        cleanup: contextlib.ExitStack,
        timeout: float,
        record_property: Callable[[str, object], None] | None = None,
    ) -> None:
        """Bind to the board and the test.

        Args:
            board: the board under test.
            cleanup: registers the undos of a subclass's changes.
            timeout: the longest an install may take.
            record_property: records the refused offer, or None to record nothing.
        """
        self._board = board
        self._cleanup = cleanup
        self._timeout = timeout
        self._record_property = record_property

    def install(self, bundle: pathlib.Path) -> tuple[int, str, float]:
        """Install `bundle` through `tools/kiosk-install.sh`.

        Args:
            bundle: the bundle on the host.

        Returns:
            The tool's return code, its combined stdout and stderr, and the seconds it took.

        Raises:
            subprocess.TimeoutExpired: the install ran past the timeout.
        """
        started = time.monotonic()
        tool = subprocess.Popen(
            [str(_INSTALL_TOOL), self._board.host, str(bundle)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            output, _ = tool.communicate(timeout=self._timeout)
        except subprocess.TimeoutExpired:
            # the whole group, so the ssh running the install exits with the tool
            os.killpg(tool.pid, signal.SIGTERM)
            tool.communicate(timeout=_CLEANUP_SECONDS)
            raise
        return tool.returncode, output, round(time.monotonic() - started, 1)

    def assert_refused(self, bundle: pathlib.Path, reasons: tuple[str, ...]) -> dict:
        """Offer `bundle` and assert it was refused for each of `reasons`, leaving the board as it was.

        With a `record_property`, records `before`, `install_rc`, `install_output`, `install_s` and
        `after`, the two snapshots as JSON.

        Args:
            bundle: the bundle on the host.
            reasons: what the install's output must contain.

        Returns:
            The board's snapshot from before the offer.
        """
        before = self._board.snapshot()
        if self._record_property:
            self._record_property("before", json.dumps(before))
        returncode, output, seconds = self.install(bundle)
        after = self._board.snapshot()
        if self._record_property:
            self._record_property("install_rc", returncode)
            self._record_property("install_output", output)
            self._record_property("install_s", seconds)
            self._record_property("after", json.dumps(after))
        # rc 2 is a D-Bus error: the board could not say, which is not a refusal
        assert returncode == 1, f"the install returned {returncode}, not a refusal (1): {output}"
        for reason in reasons:
            assert reason in output, f"refused, but not for the reason {reason!r}: {output}"
        changed = [key for key in before if after[key] != before[key]]
        assert not changed, f"the board changed when it refused the bundle: {changed}"
        return before
