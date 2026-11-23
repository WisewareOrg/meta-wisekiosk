"""What the running kernel reports: its boot across a long sleep, its built-in modules, the SoC's temperature."""

import time

from board.part import Part

# how often `sleep_watching_boot` reads the boot, so a reboot ends the sleep early
_BOOT_CHECK_SECONDS = 600


class Kernel(Part):
    """The running kernel, as the board reports it."""

    def sleep_watching_boot(self, boot_id: str, seconds: float) -> str | None:
        """Sleep out `seconds`, reading the boot every 600 s, and end early if the board booted again.

        The final read, made once more after the sleep, leaves the session live for every read after
        it.

        Args:
            boot_id: the boot the sleep starts in.
            seconds: how long to sleep.

        Returns:
            The boot id at the end, or None if it could not be read.
        """
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(min(_BOOT_CHECK_SECONDS, max(0, end - time.monotonic())))
            now = self._boot_id_or_none()
            if now is not None and now != boot_id:
                break
        return self._boot_id_or_none()

    def _boot_id_or_none(self) -> str | None:
        """Read the kernel's boot id, retrying through a dropped session for `READ_RETRY_SECONDS`.

        Returns:
            The boot id, or None if it could not be read.
        """
        try:
            return self._board.boot_id(retry_for=self._board.READ_RETRY_SECONDS)
        except self._board.ERRORS:
            return None
