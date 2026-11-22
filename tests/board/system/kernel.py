"""What the running kernel reports: its uptime and boot, its built-in modules, the SoC's temperature."""

import time

from board.part import Part

# how often `sleep_watching_boot` reads the boot, so a reboot ends the sleep early
_BOOT_CHECK_SECONDS = 600


class Kernel(Part):
    """The running kernel, as the board reports it."""

    def uptime_s(self, retry_for: float | None = None) -> float:
        """Read the board's uptime.

        Args:
            retry_for: how long to retry through a dropped session, as `Board.run` takes it; None reads once.

        Returns:
            The uptime, in seconds.
        """
        return float(self._board.run("cat /proc/uptime", check=True, retry_for=retry_for).text.split()[0])

    def boot_id(self, retry_for: float | None = None) -> str:
        """Read the kernel's boot id, which differs in each boot.

        Args:
            retry_for: how long to retry through a dropped session, as `Board.run` takes it; None reads once.

        Returns:
            The boot id.
        """
        return self._board.run(self._board.BOOT_ID_CMD, check=True, retry_for=retry_for).text

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

    def builtin_modules(self) -> list[str]:
        """Read the kernel modules built into the running kernel.

        Returns:
            The lines of its `modules.builtin`.
        """
        return self._board.run("cat /lib/modules/$(uname -r)/modules.builtin", check=True).stdout

    def soc_temperature_c(self) -> float | None:
        """Read the SoC's temperature.

        Returns:
            The temperature in degrees Celsius, or None if it could not be read.
        """
        result = self._board.run("cat /sys/class/thermal/thermal_zone0/temp")
        return int(result.stdout[0]) / 1000 if result.returncode == 0 and result.stdout else None

    def _boot_id_or_none(self) -> str | None:
        """Read the kernel's boot id, retrying through a dropped session for `READ_RETRY_SECONDS`.

        Returns:
            The boot id, or None if it could not be read.
        """
        try:
            return self.boot_id(retry_for=self._board.READ_RETRY_SECONDS)
        except self._board.ERRORS:
            return None
