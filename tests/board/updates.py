"""RAUC and the board's one install path, as the update tests drive them."""

import functools
import json
import os
import pathlib
import re
import signal
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING

from labgrid.driver.exception import ExecutionError

from board.part import Part, invalid_if

if TYPE_CHECKING:
    from candidate_bundles import CandidateBundles
    from record import Record


_INSTALL_TOOL = pathlib.Path(__file__).resolve().parents[2] / "tools" / "kiosk-install.sh"
# how long the install tool may take to clean up after a SIGTERM
_CLEANUP_SECONDS = 120
_NONCE_PATH = "/tmp/kiosk-update-nonce"
# prints BOOT_ORDER and each slot's BOOT_x_LEFT as name=value lines
_BOOT_VARIABLES_CMD = "fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT"
# 3 * (180 s boot wait + 180 s netcheck TimeoutStartSec + 30 s RebootWatchdogSec) + 180 s for the
# fallback boot; a backstop, the record carries the time it took
_FALLBACK_WAIT_SECONDS = 1350
_PROGRESS_CMD = "busctl get-property de.pengutronix.rauc / de.pengutronix.rauc.Installer Progress"
_COPY_STEP = "Copying image to "
# the sectors-written field of /sys/class/block/<dev>/stat
_STAT_SECTORS_WRITTEN = 6


class Updates(Part):
    """RAUC on the board, and the one install path `tools/kiosk-install.sh` takes to it.

    Attributes:
        build_bundles: builds this run's test bundles, or returns them once built; the target suite sets it.
        CANDIDATE_INSTALL_TIMEOUT_SECONDS: a hang backstop on one install, well past a slot's first adaptive
            install, which hashes the whole slot.
    """

    build_bundles: Callable[[], "CandidateBundles"]
    CANDIDATE_INSTALL_TIMEOUT_SECONDS = 1200

    @functools.cached_property
    def bundles(self) -> "CandidateBundles":
        """This run's test bundles, built on first use.

        Returns:
            The bundles.
        """
        return self.build_bundles()

    def install_built_image(self) -> None:
        """Install the image this checkout built on the board, through `just kiosk-ota`."""
        subprocess.run(["just", "kiosk-ota", self._board.host], check=True)

    def boot_order(self) -> tuple[list[str], dict[str, int]]:
        """Read BOOT_ORDER and each slot's BOOT_x_LEFT from `fw_printenv`.

        Returns:
            The slots' bootnames in the order the bootloader tries them, then the attempts left per
            bootname.
        """
        stdout = self._board.run(_BOOT_VARIABLES_CMD, check=True).stdout
        variables = dict(line.split("=", 1) for line in stdout)
        attempts_left = {name: int(variables[f"BOOT_{name}_LEFT"]) for name in ("A", "B")}
        return variables["BOOT_ORDER"].split(), attempts_left

    def build_commit(self) -> str:
        """Read the meta-wisekiosk commit the board's image was built from.

        Returns:
            The commit named by the meta-wisekiosk line of /etc/buildinfo.
        """
        result = self._board.run("cat /etc/buildinfo", timeout=None)
        assert result.returncode == 0, "could not read /etc/buildinfo on the board"
        line = next((entry for entry in result.stdout if entry.split()[:2] == ["meta-wisekiosk", "="]), None)
        assert line is not None, f"no meta-wisekiosk layer line in buildinfo:\n{chr(10).join(result.stdout)}"
        return line.split()[2].rsplit(":", 1)[-1]

    def install_bundle(self, bundle: pathlib.Path, timeout: float) -> tuple[int, str, float]:
        """Install `bundle` through `tools/kiosk-install.sh`, the board's one install path.

        Args:
            bundle: the bundle on the host.
            timeout: the longest the install may take.

        Returns:
            The tool's return code, its combined stdout and stderr, and the seconds it took.

        Raises:
            subprocess.TimeoutExpired: the install ran past `timeout`.
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
            output, _ = tool.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # the whole group, so the ssh running the install exits with the tool
            os.killpg(tool.pid, signal.SIGTERM)
            tool.communicate(timeout=_CLEANUP_SECONDS)
            raise
        return tool.returncode, output, round(time.monotonic() - started, 1)

    def install_and_restart(self, bundle: pathlib.Path) -> float:
        """Install `bundle` over the air and restart the board into it; it returns to the candidate when the test ends.

        Args:
            bundle: one of this run's test bundles.

        Returns:
            The host `time.monotonic()` just before the restart.
        """
        self.return_to_candidate_after_test(self.bundles)
        self.allow_test_bundles(self.bundles.nonce)
        booted = self.rauc_status()["booted"]
        returncode, output, _seconds = self.install_bundle(bundle, self.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
        assert returncode == 0, f"the install returned {returncode}: {output}"
        restarted = self._board.restart_with("systemctl reboot")
        assert self.rauc_status()["booted"] != booted, "the board did not restart into the update"
        return restarted

    def cut_power_while_writing(self, bundle: pathlib.Path) -> float:
        """Cut the board's power while `bundle` is being written into the slot not booted, then restore it.

        The cut comes once RAUC reports copying the image and the slot's device has been written to since
        the install began; the check is invalid if the install ended, or did not reach that, first. The
        board returns to the candidate when the test ends.

        Args:
            bundle: one of this run's test bundles, which no slot already holds.

        Returns:
            The host `time.monotonic()` at which power began to return.
        """
        self.return_to_candidate_after_test(self.bundles)
        self.allow_test_bundles(self.bundles.nonce)
        status = self.rauc_status()
        others = [slot["device"] for entry in status["slots"] for slot in entry.values() if slot["state"] != "booted"]
        assert others, f"no slot other than the booted one in rauc status: {status!r}"
        device = others[0]
        _step, written = self._write_progress(device)
        pool = ThreadPoolExecutor(max_workers=1)
        installing = pool.submit(self.install_bundle, bundle, self.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
        self._board.cleanup.callback(pool.shutdown)
        with invalid_if("the update was not being written when the power was cut"):
            self._board.seconds_until(lambda: self._is_writing(installing, device, since=written))
        return self._board.cut_power()

    def assert_refused(self, bundle: pathlib.Path, reasons: tuple[str, ...], timeout: float, record: "Record") -> None:
        """Offer `bundle`; assert it was refused for each of `reasons`, nothing staged, same build, on the panel.

        Waits for the instance on the panel before the offer and again after it. Records the board's
        state before the offer as `before`, the install's `install_rc`, `install_output` and
        `install_s`, and the state after as `after`, then asserts.

        Args:
            bundle: the bundle on the host.
            reasons: text the refusal's output must carry, each.
            timeout: the longest the install may take.
            record: the test's record.
        """
        self._board.app.page.wait_for_instance()
        before = self.next_boot_and_running_build()
        record(before=json.dumps(before))
        returncode, output, duration_s = self.install_bundle(bundle, timeout)
        record(install_rc=returncode, install_output=output, install_s=duration_s)
        after = self.next_boot_and_running_build()
        record(after=json.dumps(after))

        # rc 2 is a D-Bus error: the board could not say, which is not a refusal
        assert returncode == 1, f"the install returned {returncode}, not a refusal (1): {output}"
        for reason in reasons:
            assert reason in output, f"refused, but not for the reason {reason!r}: {output}"
        assert after["boot_variables"] == before["boot_variables"], "the next boot's slot order changed"
        assert after["rauc_status"] == before["rauc_status"], "rauc's slot status changed"
        assert after["boot_id"] == before["boot_id"], "the board restarted"
        assert after["commit"] == before["commit"], "the board runs a different build"
        self._board.app.page.wait_for_instance()

    def allow_test_bundles(self, nonce: str) -> None:
        """Put this run's nonce in the board's `/tmp`, until the test ends, so a test bundle's hook accepts it.

        Args:
            nonce: the run's nonce.
        """
        self._board.run(f"printf %s {nonce} > {_NONCE_PATH}", check=True)
        self._board.cleanup.callback(self._board.run, f"rm -f {_NONCE_PATH}", check=True)

    def assert_refused_then_install(self, bundle: pathlib.Path, nonce: str, record: "Record") -> dict:
        """Offer `bundle` without the nonce and assert the refusal, then install it with the nonce.

        Records the install's `install_rc`, `install_output` and `install_s`, then asserts it took
        without a restart.

        Args:
            bundle: the test bundle on the host.
            nonce: the run's nonce, which the bundle's install-check hook asks for.
            record: the test's record.

        Returns:
            `next_boot_and_running_build()` as it read just before the install.
        """
        self._board.run(f"rm -f {_NONCE_PATH}", check=True)
        before = self.next_boot_and_running_build()
        returncode, output, _seconds = self.install_bundle(bundle, self.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
        assert returncode == 1, f"the bundle without the nonce returned {returncode}, not a refusal (1): {output}"
        for reason in ("Bundle rejected", "test bundle: no run nonce"):
            assert reason in output, f"refused, but not for the reason {reason!r}: {output}"
        assert self.next_boot_and_running_build() == before, "the board changed when it refused the bundle"

        self.allow_test_bundles(nonce)
        before = self.next_boot_and_running_build()
        returncode, output, seconds = self.install_bundle(bundle, self.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
        record(install_rc=returncode, install_output=output, install_s=seconds)
        assert returncode == 0, f"the install returned {returncode}: {output}"
        assert self.next_boot_and_running_build()["boot_id"] == before["boot_id"], (
            "the board restarted during the install"
        )
        return before

    def assert_falls_back_then_takes_candidate(
        self, bundle: pathlib.Path, candidate: "CandidateBundles", count_boots: bool, record: "Record"
    ) -> None:
        """Install `bundle`, restart into it, and assert the board falls back, then takes the candidate.

        Records the install (`assert_refused_then_install`), the update slot's `attempts`, and
        `back_s`, the seconds from the restart until the board answers again on the slot it fell
        back to.

        Args:
            bundle: the test bundle whose boots fail.
            candidate: the candidate, reinstalled once the board has fallen back.
            count_boots: also assert that the journal holds one new boot per failed attempt.
            record: the test's record.
        """
        before = self.assert_refused_then_install(bundle, candidate.nonce, record)
        target = ({"A", "B"} - {before["rauc_status"]["booted"]}).pop()
        order, attempts_left = self.boot_order()
        assert order[0] == target, f"the update's slot {target} does not lead BOOT_ORDER: {order}"
        attempts = attempts_left[target]
        record(attempts=attempts)
        assert 0 < attempts <= 3, f"slot {target} has {attempts} attempts left, not 1 to 3"
        boots_before = self.journal_boot_ids() if count_boots else None

        started = self._board.restart_with("systemctl reboot", within=_FALLBACK_WAIT_SECONDS)
        record(back_s=round(time.monotonic() - started, 1))

        after = self.next_boot_and_running_build()
        assert self._booted_slot(after["rauc_status"]) == self._booted_slot(before["rauc_status"]), (
            "the board is not back on the previous slot and bundle"
        )
        assert after["commit"] == before["commit"], "the board is not back on the previous build"
        order, attempts_left = self.boot_order()
        assert order[0] == target, f"the update's slot {target} no longer leads BOOT_ORDER: {order}"
        assert attempts_left[target] == 0, f"slot {target} has {attempts_left[target]} attempts left, not 0"
        if count_boots:
            # journalctl lists boot ids without the dashes /proc/sys/kernel/random/boot_id has
            failed = self.journal_boot_ids() - boots_before - {after["boot_id"].replace("-", "")}
            assert len(failed) == attempts, (
                f"{len(failed)} failed boots in the journal, expected {attempts}: the update did not start "
                "and fail to reach the network the way the test means"
            )

        returncode, output, _seconds = self.install_bundle(candidate.candidate, self.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
        assert returncode == 0, f"installing the candidate returned {returncode}: {output}"
        self._board.restart_with("systemctl reboot")
        _slot, booted_hash = self._booted_slot(self.next_boot_and_running_build()["rauc_status"])
        assert booted_hash == candidate.hash, "the board is not on the candidate's bundle"
        assert self.build_commit() == candidate.commit, "the board is not on the candidate's build"

    def return_to_candidate_after_test(self, candidate: "CandidateBundles") -> None:
        """When the test ends, put the board back on the candidate unless it runs it and will boot it next.

        Args:
            candidate: the candidate the board started the test on.
        """
        self._board.cleanup.callback(self._restore_candidate, candidate)

    def rauc_status(self) -> dict:
        """Read `rauc status --detailed` as the board's own `rauc` reports it.

        Returns:
            The status, parsed from its JSON: the board's `compatible`, its `booted` slot, and each slot
            with its state, device and installed bundle.
        """
        return json.loads(self._board.run("rauc status --detailed --output-format=json", check=True).text)

    def next_boot_and_running_build(self) -> dict:
        """Read what the next boot and the running build are.

        Returns:
            The raw `boot_variables` text, the parsed `rauc_status`, the `boot_id` and the `commit`.
        """
        return {
            "boot_variables": self._board.run(_BOOT_VARIABLES_CMD, check=True).text,
            "rauc_status": self.rauc_status(),
            "boot_id": self._board.system.kernel.boot_id(),
            "commit": self.build_commit(),
        }

    def journal_boot_ids(self) -> set[str]:
        """Read the boot ids in the board's journal.

        Returns:
            The boot ids, without dashes.
        """
        stdout = self._board.run("journalctl --list-boots -o json", check=True, timeout=None).stdout
        return {boot["boot_id"] for boot in json.loads("\n".join(stdout))}

    def _is_writing(self, installing: Future, device: str, since: int) -> bool:
        """Whether an install still running is copying the image into `device`, written to since `since`.

        Args:
            installing: the install.
            device: the slot's device.
            since: the device's sectors written before the install began.

        Returns:
            True if RAUC reports its copy step and the device's written-sector count has risen; an
            assertion fails if the install has ended.
        """
        assert not installing.done(), f"the install ended: {installing.result()[:2]}"
        step, written = self._write_progress(device)
        return step.startswith(_COPY_STEP) and written > since

    def _write_progress(self, device: str) -> tuple[str, int]:
        """Read RAUC's install step and the sectors written so far to `device`.

        Args:
            device: the slot's device.

        Returns:
            The step's message, and the sectors written.

        Raises:
            ExecutionError: the read failed, which `Board.seconds_until` takes as a read that does not hold.
        """
        read = self._board.run(f"{_PROGRESS_CMD} && cat /sys/class/block/{os.path.basename(device)}/stat")
        step = re.fullmatch(r'\(isi\) \d+ "(.*)" \d+', read.stdout[0].strip()) if len(read.stdout) == 2 else None
        if step is None:
            raise ExecutionError(_PROGRESS_CMD, read.stdout, read.stderr)
        return step[1], int(read.stdout[1].split()[_STAT_SECTORS_WRITTEN])

    def _restore_candidate(self, candidate: "CandidateBundles") -> None:
        """Put the board back on the candidate unless it runs it and will boot it next.

        Args:
            candidate: the candidate the board started the test on.
        """
        status = self.next_boot_and_running_build()["rauc_status"]
        _slot, booted_hash = self._booted_slot(status)
        order, _attempts_left = self.boot_order()
        if booted_hash == candidate.hash and order[0] == status["booted"]:
            return
        returncode, output, _seconds = self.install_bundle(candidate.candidate, self.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
        assert returncode == 0, f"reinstalling the candidate returned {returncode}: {output}"
        self._board.restart_with("systemctl reboot")

    @staticmethod
    def _booted_slot(status: dict) -> tuple[str, str]:
        """The booted slot's name and the hash of the bundle it was installed from.

        Args:
            status: RAUC's detailed status.

        Returns:
            The slot's name and the bundle hash.

        Raises:
            AssertionError: no slot is listed as booted.
        """
        for entry in status["slots"]:
            for name, slot in entry.items():
                if slot["state"] == "booted":
                    return name, slot["slot_status"]["bundle"]["hash"]
        raise AssertionError(f"no booted slot in rauc status: {status!r}")
