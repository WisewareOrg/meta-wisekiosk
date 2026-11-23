"""RAUC and the board's one install path, as the update tests drive them."""

import functools
import json
import os
import pathlib
import re
import signal
import subprocess
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, NamedTuple

import pytest
from labgrid.driver.exception import ExecutionError

from board.app.config import shows_a_loss
from board.part import Part, invalid_if

if TYPE_CHECKING:
    from candidate_bundles import CandidateBundles
    from refused_offers import Offer, RefusedOffers


_INSTALL_TOOL = pathlib.Path(__file__).resolve().parents[2] / "tools" / "kiosk-install.sh"
# how long the install tool may take to clean up after a SIGTERM
_CLEANUP_SECONDS = 120
_NONCE_PATH = "/tmp/kiosk-update-nonce"
# prints BOOT_ORDER and each slot's BOOT_x_LEFT as name=value lines
_BOOT_VARIABLES_CMD = "fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT"
# 3 * (180 s boot wait + 180 s netcheck TimeoutStartSec + 30 s RebootWatchdogSec) + 180 s for the
# fallback boot
_FALLBACK_WAIT_SECONDS = 1350
_PROGRESS_CMD = "busctl get-property de.pengutronix.rauc / de.pengutronix.rauc.Installer Progress"
# a hang cutoff, the install tool's own checks included
_OFFER_TIMEOUT_SECONDS = 120
_COPY_STEP = "Copying image to "
# the sectors-written field of /sys/class/block/<dev>/stat
_STAT_SECTORS_WRITTEN = 6


class Update(NamedTuple):
    """An image update installed, and the restart after it.

    Attributes:
        returncode: the install tool's return code; 0 installed.
        output: the tool's combined output.
        booted_before: the slot the board booted before the install.
        booted_after: the slot the board booted after the restart.
        restarted_at: the host `time.monotonic()` just before the restart; None if the install failed, so
            there was none.
    """

    returncode: int
    output: str
    booted_before: str
    booted_after: str
    restarted_at: float | None


class Offered(NamedTuple):
    """How an offered image update's install ended.

    Attributes:
        returncode: the install tool's return code: 0 installed, 1 refused, 2 a D-Bus error, the board
            unable to say.
        output: the tool's combined output.
        reasons: what a refusal must name for the offer to have been judged as the item offers it.
    """

    returncode: int
    output: str
    reasons: tuple[str, ...]

    def confirm_refused_for_its_reasons(self) -> None:
        """Fail the check as invalid if the refusal did not name the offer's reasons."""
        with invalid_if(f"refused, but not for the reasons the offer names: {self.output}"):
            assert all(reason in self.output for reason in self.reasons)


class Installed(NamedTuple):
    """The start-of-run install: the build it installed, and what the board held before it.

    Attributes:
        commit: the commit the installed build is from.
        marker: a line written to the board's log before the install.
        marker_logged: whether the log held the marker before the install.
        config_before: the live config's sha256 before the install, None if it was missing.
        config_after: the live config's sha256 straight after the install's restart, None if it was missing.
        default_config: the installed image's default config's sha256, None if it was missing.
    """

    commit: str
    marker: str
    marker_logged: bool
    config_before: str | None
    config_after: str | None
    default_config: str | None

    def logged_marker(self) -> str:
        """The marker written to the log before the install.

        Returns:
            The marker; the check is invalid if the log did not hold it before the install.
        """
        with invalid_if("the marker never reached the log before the install"):
            assert self.marker_logged
        return self.marker

    def confirm_a_loss_would_show(self) -> None:
        """Fail the check as invalid if the config held before the install could not show its loss."""
        with invalid_if("a loss of the board's config could not show"):
            assert shows_a_loss(self.config_before, self.default_config)


class Updates(Part):
    """RAUC on the board, and the one install path `tools/kiosk-install.sh` takes to it.

    Attributes:
        CANDIDATE_INSTALL_TIMEOUT_SECONDS: a hang backstop on one install, well past a slot's first adaptive
            install, which hashes the whole slot.
    """

    CANDIDATE_INSTALL_TIMEOUT_SECONDS = 1200

    @functools.cached_property
    def bundles(self) -> "CandidateBundles":
        """This run's test bundles; the test is skipped outside a build.

        The run's first read builds them, minutes of bitbake in the kas container, inside whichever test
        reads them first: in a full run, TST003's fault.

        Returns:
            The bundles.
        """
        return self._board.fixture("candidate_bundles")

    @functools.cached_property
    def refused_offers(self) -> "RefusedOffers":
        """The updates the board must refuse, built on first use.

        Returns:
            The offers.
        """
        return self._board.fixture("refused_offers")

    @functools.cached_property
    def installed(self) -> Installed:
        """The start-of-run install; the test is skipped outside a build, where there was none.

        Returns:
            The install.
        """
        installed = self._board.fixture("install_candidate")
        if installed is None:
            pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
        return installed

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

    def next_boot_slot(self) -> str | None:
        """Read which slot the bootloader boots at the next restart: the first in BOOT_ORDER with attempts left.

        Returns:
            Its bootname, or None if no slot has attempts left.
        """
        order, attempts_left = self.boot_order()
        return next((slot for slot in order if attempts_left[slot] > 0), None)

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

        An assertion fails the test if it is not marked `sends_update`, which runs it after every other.

        Args:
            bundle: the bundle on the host.
            timeout: the longest the install may take.

        Returns:
            The tool's return code, its combined stdout and stderr, and the seconds it took.

        Raises:
            subprocess.TimeoutExpired: the install ran past `timeout`.
        """
        test = self._board.fixture("request").node
        assert test.get_closest_marker("sends_update"), f"{test.nodeid} sends an update but is not marked sends_update"
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

    def install_and_restart(self, bundle: pathlib.Path) -> Update:
        """Install `bundle` over the air and, if it installed, restart the board.

        The board returns to the candidate when the test ends.

        Args:
            bundle: one of this run's test bundles.

        Returns:
            How the install ended, the slot booted before and after, and when the restart began.
        """
        self.return_to_candidate_after_test(self.bundles)
        self.allow_test_bundles(self.bundles.nonce)
        booted_before = self.rauc_status()["booted"]
        returncode, output, _seconds = self.install_bundle(bundle, self.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
        if returncode != 0:
            return Update(returncode, output, booted_before, booted_before, None)
        restarted_at = self._board.restart_with("systemctl reboot")
        return Update(returncode, output, booted_before, self.rauc_status()["booted"], restarted_at)

    def cut_power_while_writing(self, bundle: pathlib.Path) -> float:
        """Cut the board's power while `bundle` is being written into the slot not booted, then restore it.

        The cut comes once RAUC reports copying the image and the slot's device has been written to since
        the install began; the check is invalid if the install ended, or did not reach that, first. Once
        the board answers again, the check is invalid if the update's slot was activated, as an install
        that completed before the cut leaves it. The install's own end is not waited for, since its ssh
        outlives the cut by tens of seconds. The board returns to the candidate when the test ends.

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
        update_slot = ({"A", "B"} - {status["booted"]}).pop()
        power_returned = self._board.cut_power()
        order, attempts_left = self.boot_order()
        with invalid_if("the power was cut after the update was written: its slot was activated"):
            assert not (order[0] == update_slot and attempts_left[update_slot] > 0)
        return power_returned

    def offer(self, offer: "Offer") -> Offered:
        """Offer the board an image update through its one install path.

        Args:
            offer: the update, and what its refusal must name.

        Returns:
            How the install ended, with what its refusal must name.
        """
        returncode, output, _seconds = self.install_bundle(offer.bundle, _OFFER_TIMEOUT_SECONDS)
        return Offered(returncode, output, offer.reasons)

    def allow_test_bundles(self, nonce: str) -> None:
        """Put this run's nonce in the board's `/tmp`, until the test ends, so a test bundle's hook accepts it.

        Args:
            nonce: the run's nonce.
        """
        self._board.run(f"printf %s {nonce} > {_NONCE_PATH}", check=True)
        self._board.cleanup.callback(self._board.run, f"rm -f {_NONCE_PATH}", check=True)

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

    def running_bundle(self) -> str:
        """Read the hash of the bundle the booted slot was installed from.

        Returns:
            The hash, as RAUC records it.
        """
        status = self.rauc_status()
        booted = [slot for entry in status["slots"] for slot in entry.values() if slot["state"] == "booted"]
        assert booted, f"no booted slot in rauc status: {status!r}"
        return booted[0]["slot_status"]["bundle"]["hash"]

    def install_and_fall_back(self, bundle: pathlib.Path, starts: bool) -> int:
        """Install `bundle` over the air, restart into it, and wait for the board to fall back from it.

        The board returns to the candidate when the test ends. The check is invalid if no attempt to start
        the update was used, or an update that starts did not leave one boot in the journal for each failed
        attempt.

        Args:
            bundle: one of this run's test bundles, whose boots fail.
            starts: whether the update starts before it fails, so each attempt is a boot the journal keeps.

        Returns:
            How many attempts to start the update failed, as its slot's attempts left count them down.
        """
        self.return_to_candidate_after_test(self.bundles)
        self.allow_test_bundles(self.bundles.nonce)
        update_slot = ({"A", "B"} - {self.rauc_status()["booted"]}).pop()
        returncode, output, _seconds = self.install_bundle(bundle, self.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
        with invalid_if(f"the update did not install, so there was nothing to fall back from: {output}"):
            assert returncode == 0
        _order, attempts = self.boot_order()
        boots = self._journal_boot_ids()
        self._board.restart_with("systemctl reboot", within=_FALLBACK_WAIT_SECONDS)
        _order, attempts_left = self.boot_order()
        failed = attempts[update_slot] - attempts_left[update_slot]
        with invalid_if("the update was never tried: no attempt to start it was used"):
            assert failed >= 1
        if starts:
            with invalid_if("the update did not start once for each failed attempt"):
                # journalctl lists boot ids without the dashes /proc/sys/kernel/random/boot_id has
                started = self._journal_boot_ids() - boots - {self._board.boot_id().replace("-", "")}
                assert len(started) == failed, f"{len(started)} boots for {failed} attempts"
        return failed

    def _journal_boot_ids(self) -> set[str]:
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
        order, _attempts_left = self.boot_order()
        if self.running_bundle() == candidate.hash and order[0] == self.rauc_status()["booted"]:
            return
        returncode, output, _seconds = self.install_bundle(candidate.candidate, self.CANDIDATE_INSTALL_TIMEOUT_SECONDS)
        assert returncode == 0, f"reinstalling the candidate returned {returncode}: {output}"
        self._board.restart_with("systemctl reboot")
