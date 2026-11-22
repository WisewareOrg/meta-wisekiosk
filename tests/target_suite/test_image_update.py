"""Target suite: image updates over the air, each starting with the board on the candidate and leaving it there.

The bundles are copies of the candidate, edited and re-signed by the operator key. Each carries an
install-check hook that refuses unless this run's nonce is in the board's `/tmp`.
"""

import json
import os
import re
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

import pytest
from board import Board
from container_dir import ContainerDir
from panel import Panel
from record import Record
from update import Update

_PROBE = "/work/tests/target_suite/probe.js"
_NONCE_PATH = "/tmp/kiosk-update-nonce"
# a hang backstop, well past a slot's first adaptive install, which hashes the whole slot
_INSTALL_TIMEOUT_SECONDS = 1200
# 3 * (180 s boot wait + 180 s netcheck TimeoutStartSec + 30 s RebootWatchdogSec) + 180 s for the
# fallback boot; a backstop, the record carries the time it took
_FALLBACK_WAIT_SECONDS = 1350
# TST006's bound
_ON_PANEL_BOUND_SECONDS = 160
# TST003's bound
_POWER_CUT_BOUND_SECONDS = 60
_PROGRESS_CMD = "busctl get-property de.pengutronix.rauc / de.pengutronix.rauc.Installer Progress"
_COPY_STEP = "Copying image to "
# the sectors-written field of /sys/class/block/<dev>/stat
_STAT_SECTORS_WRITTEN = 6

pytestmark = pytest.mark.sends_update


class UpdateBundles(NamedTuple):
    """The three test bundles, this run's nonce and stamp, and the candidate's bundle hash, path and commit.

    Attributes:
        new_build: the bundle with a different build.
        cannot_start: the bundle that lacks init and sh.
        no_network: the bundle that starts but cannot join the network.
        nonce: this run's nonce, which the bundles' install-check hook requires on the board.
        stamp: this run's stamp, which the new-build bundle's page carries.
        hash: the candidate's bundle hash.
        candidate: the candidate's bundle on the host.
        commit: the candidate's commit.
    """

    new_build: Path
    cannot_start: Path
    no_network: Path
    nonce: str
    stamp: str
    hash: str
    candidate: Path
    commit: str


@pytest.fixture(scope="module")
def bundles(request: pytest.FixtureRequest, bench_candidate: str | None) -> UpdateBundles:
    """Build the three test bundles in the host's `/tmp` through `tools/kas-run.sh`.

    Skips outside a build, where there is no candidate bundle to copy.

    Args:
        request: removes the build directory at the end of the module.
        bench_candidate: the commit under test, or None outside a build.

    Returns:
        The bundles, this run's nonce and stamp, and the candidate's bundle hash, path and commit.
    """
    if bench_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    work = ContainerDir(request)
    nonce = uuid.uuid4().hex
    stamp = uuid.uuid4().hex
    work.run("update_bundles.sh", nonce, stamp, _PROBE)
    return UpdateBundles(
        work.path / "new-build.raucb",
        work.path / "cannot-start.raucb",
        work.path / "no-network.raucb",
        nonce,
        stamp,
        (work.path / "candidate.hash").read_text().strip(),
        work.REPO / (work.path / "candidate.path").read_text().strip(),
        bench_candidate,
    )


class _CandidateUpdate(Update):
    """An `Update` that starts the test on the candidate and leaves the board there.

    At teardown it puts the board back on the candidate unless it runs it and will boot it next.
    Nothing is recorded by `refuse`; the tests record their accepted install themselves.

    Attributes:
        bundles: the bundles the test offers.
    """

    bundles: UpdateBundles

    def __init__(
        self,
        board: Board,
        request: pytest.FixtureRequest,
        record_property: Callable[[str, object], None],
        bundles: UpdateBundles,
    ) -> None:
        """Bind to the board and the test, and register the restore of the candidate.

        Args:
            board: the board under test.
            request: the test's request, on which the restore is registered.
            record_property: records the accepted install and the fallback.
            bundles: the bundles the test offers.
        """
        super().__init__(board, request, _INSTALL_TIMEOUT_SECONDS)
        self._record = record_property
        self.bundles = bundles
        request.addfinalizer(self._back_on_candidate)

    @staticmethod
    def slot(rauc_status: dict, booted: bool) -> tuple[str, dict]:
        """The booted slot, or the first slot the board did not boot.

        Args:
            rauc_status: the board's `rauc status` as JSON.
            booted: pick the booted slot, not another.

        Returns:
            The slot's name and its status entry.

        Raises:
            AssertionError: there is no such slot.
        """
        for entry in rauc_status["slots"]:
            for name, slot in entry.items():
                if (slot["state"] == "booted") == booted:
                    return name, slot
        raise AssertionError(f"no {'booted' if booted else 'other'} slot in rauc status: {rauc_status!r}")

    def boot_ids(self) -> set[str]:
        """The set of boot ids in the board's journal.

        Returns:
            The ids, as `journalctl` lists them, without dashes.
        """
        stdout = self._board.run("journalctl --list-boots -o json", check=True, timeout=None)[0]
        return {boot["boot_id"] for boot in json.loads("\n".join(stdout))}

    def install_state(self, device: str) -> tuple[str, int] | None:
        """RAUC's install step message and the sectors written to `device` so far.

        Args:
            device: the slot's device on the board.

        Returns:
            The step and the sector count, or None when the read failed.
        """
        try:
            stdout, _stderr, returncode = self._board.run(
                f"{_PROGRESS_CMD}; cat /sys/class/block/{os.path.basename(device)}/stat"
            )
        except Board.ERRORS:
            return None
        if returncode != 0 or len(stdout) != 2:
            return None
        progress = re.fullmatch(r'\(isi\) \d+ "(.*)" \d+', stdout[0].strip())
        if progress is None:
            return None
        return progress[1], int(stdout[1].split()[_STAT_SECTORS_WRITTEN])

    def allow(self) -> None:
        """Put this run's nonce on the board, so the bundles' install-check hook accepts; remove it at teardown."""
        self._board.run(f"printf %s {self.bundles.nonce} > {_NONCE_PATH}", check=True)
        self._request.addfinalizer(lambda: self._board.run(f"rm -f {_NONCE_PATH}", check=True))

    def refuse_then_install(self, bundle: Path) -> dict:
        """Offer `bundle` without the nonce and assert the refusal, then install it with the nonce.

        Records the accepted install as `install_rc`, `install_output` and `install_s`.

        Args:
            bundle: the bundle on the host.

        Returns:
            The board's snapshot from before the install.
        """
        board = self._board
        board.run(f"rm -f {_NONCE_PATH}", check=True)
        self.assert_refused(bundle, ("Bundle rejected", "test bundle: no run nonce"))

        self.allow()
        before = board.snapshot()
        returncode, output, seconds = self.install(bundle)
        self._record("install_rc", returncode)
        self._record("install_output", output)
        self._record("install_s", seconds)
        assert returncode == 0, f"the install returned {returncode}: {output}"
        assert board.snapshot()["boot_id"] == before["boot_id"], "the board restarted during the install"
        return before

    def fall_back_and_accept(self, bundle: Path, count_boots: bool) -> None:
        """Install `bundle`, restart into it, and assert the board falls back and takes the candidate.

        Args:
            bundle: the bundle on the host.
            count_boots: also assert that the journal holds one new boot per failed attempt.
        """
        board = self._board
        before = self.refuse_then_install(bundle)
        target = ({"A", "B"} - {before["rauc_status"]["booted"]}).pop()
        order, left = board.boot_variables()
        assert order[0] == target, f"the update's slot {target} does not lead BOOT_ORDER: {order}"
        attempts = left[target]
        self._record("attempts", attempts)
        assert 0 < attempts <= 3, f"slot {target} has {attempts} attempts left, not 1 to 3"
        boots_before = self.boot_ids() if count_boots else None

        started = time.monotonic()
        board.restart_by("systemctl reboot", wait_seconds=_FALLBACK_WAIT_SECONDS)
        self._record("back_s", round(time.monotonic() - started, 1))

        after = board.snapshot()

        def booted(rauc_status: dict) -> tuple[str, str]:
            """The booted slot's name and the hash of the bundle it was installed from.

            Args:
                rauc_status: the board's `rauc status` as JSON.

            Returns:
                The name and the bundle hash.
            """
            name, slot = self.slot(rauc_status, booted=True)
            return name, slot["slot_status"]["bundle"]["hash"]

        assert booted(after["rauc_status"]) == booted(before["rauc_status"]), (
            "the board is not back on the previous slot and bundle"
        )
        assert after["commit"] == before["commit"], "the board is not back on the previous build"
        order, left = board.boot_variables()
        assert order[0] == target, f"the update's slot {target} no longer leads BOOT_ORDER: {order}"
        assert left[target] == 0, f"slot {target} has {left[target]} attempts left, not 0"
        if count_boots:
            # journalctl lists boot ids without the dashes /proc/sys/kernel/random/boot_id has
            failed = self.boot_ids() - boots_before - {after["boot_id"].replace("-", "")}
            assert len(failed) == attempts, (
                f"{len(failed)} failed boots in the journal, expected {attempts}: the update did not start "
                "and fail to reach the network the way the test means"
            )

        self.onto_candidate()
        assert booted(board.snapshot()["rauc_status"])[1] == self.bundles.hash, (
            "the board is not on the candidate's bundle"
        )
        assert board.commit() == self.bundles.commit, "the board is not on the candidate's build"

    def onto_candidate(self) -> None:
        """Install the candidate's bundle and restart into it."""
        returncode, output, _seconds = self.install(self.bundles.candidate)
        assert returncode == 0, f"installing the candidate returned {returncode}: {output}"
        self._board.restart_by("systemctl reboot")

    def _back_on_candidate(self) -> None:
        """Put the board back on the candidate unless it runs it and will boot it next."""
        rauc_status = self._board.snapshot()["rauc_status"]
        _name, booted = self.slot(rauc_status, booted=True)
        order, _left = self._board.boot_variables()
        if booted["slot_status"]["bundle"]["hash"] == self.bundles.hash and order[0] == rauc_status["booted"]:
            return
        self.onto_candidate()


@pytest.fixture
def update(
    board: Board,
    request: pytest.FixtureRequest,
    record_property: Callable[[str, object], None],
    bundles: UpdateBundles,
) -> _CandidateUpdate:
    """The `_CandidateUpdate` for the test; at teardown it puts the board back on the candidate.

    Args:
        board: the board under test.
        request: the test's request, whose test must carry `sends_update`.
        record_property: records the accepted install and the fallback.
        bundles: the bundles the test offers.

    Returns:
        The update.
    """
    return _CandidateUpdate(board, request, record_property, bundles)


def test_new_application_build(
    update: _CandidateUpdate,
    board: Board,
    request: pytest.FixtureRequest,
    record_property: Callable[[str, object], None],
    record: Record,
) -> None:
    """TST006 new application build: install an update with a different build; time until it is on the panel.

    The clock starts as the restart is asked for, so it covers shutdown, boot and the page load.

    Args:
        update: offers the new-build bundle and restores the candidate at teardown.
        board: the board under test, restarted here.
        request: the test's request, which the panel registers its undos on.
        record_property: records the requirement and the time on the panel.
        record: records what the panel's reads measure.
    """
    record_property("requirement", "TST006")
    update.refuse_then_install(update.bundles.new_build)

    started = time.monotonic()
    board.restart_by("systemctl reboot")
    panel = Panel(board, request, record)
    on_panel_s, final = panel.wait_until(
        lambda read: panel.on_panel(read[1]) and read[1]["stamp"] == update.bundles.stamp,
        Board.GIVE_UP_SECONDS,
        since=started,
    )
    record_property("on_panel_s", on_panel_s)
    assert on_panel_s is not None, (
        f"the new build was not on the panel within {Board.GIVE_UP_SECONDS} s; "
        f"last sample: {final[1] if final else None!r}"
    )
    assert on_panel_s <= _ON_PANEL_BOUND_SECONDS, (
        f"on the panel after {on_panel_s} s; bound {_ON_PANEL_BOUND_SECONDS} s"
    )


def test_cannot_start(update: _CandidateUpdate, record_property: Callable[[str, object], None]) -> None:
    """TST023 cannot start: install an update that cannot start; the board falls back, then takes a valid update.

    The fallback alone does not show why the update could not start; update_bundles.sh's
    `require_gone` checks are what show the bundle lacks init and sh.

    Args:
        update: offers the bundle and restores the candidate at teardown.
        record_property: records the requirement and the fallback.
    """
    record_property("requirement", "TST023")
    update.fall_back_and_accept(update.bundles.cannot_start, count_boots=False)


def test_cannot_reach_the_network(update: _CandidateUpdate, record_property: Callable[[str, object], None]) -> None:
    """TST024 cannot reach the network: install an update that starts but cannot join; the board falls back.

    Args:
        update: offers the bundle and restores the candidate at teardown.
        record_property: records the requirement and the fallback.
    """
    record_property("requirement", "TST024")
    update.fall_back_and_accept(update.bundles.no_network, count_boots=True)


def test_power_cut_during_an_update(
    update: _CandidateUpdate,
    board: Board,
    power_cut: Callable[[], float],
    record_property: Callable[[str, object], None],
) -> None:
    """TST003 power cut during an image update: cut power once the update is being written into its slot.

    Installs the new-build bundle, which no slot already holds, and cuts once RAUC reports its copy
    step and the target slot's written-sector count has risen since the install began. Times from
    power returning until the page is served with the browser running.

    Args:
        update: offers the new-build bundle and restores the candidate at teardown.
        board: the board under test, whose power is cut.
        power_cut: cuts the power and returns the instant it came back.
        record_property: records the requirement and what the cut and the install measured.
    """
    record_property("requirement", "TST003")
    update.allow()
    before = board.snapshot()
    _name, other = update.slot(before["rauc_status"], booted=False)
    device = other["device"]
    idle = update.install_state(device)
    assert idle, f"could not read RAUC's progress or {device}'s write count"
    written_before = idle[1]
    with ThreadPoolExecutor(max_workers=1) as pool:
        installing = pool.submit(update.install, update.bundles.new_build)
        copying_s, final = board.wait_until(
            lambda: (installing.done(), update.install_state(device)),
            lambda read: read[0] or (read[1] and read[1][0].startswith(_COPY_STEP) and read[1][1] > written_before),
            _INSTALL_TIMEOUT_SECONDS,
        )
        assert not final[0], f"the install ended before it wrote to {device}: {installing.result()}"
        assert copying_s is not None, f"the install did not reach its copy step within {_INSTALL_TIMEOUT_SECONDS} s"
        state = final[1]
        record_property("step_at_cut", state[0])
        record_property("sectors_written_at_cut", state[1] - written_before)
        started = power_cut()
        back_s, last_read = board.time_until_up(started)
        returncode, output, seconds = installing.result()
    record_property("back_s", back_s)
    record_property("last_read", last_read)
    record_property("install_rc", returncode)
    record_property("install_output", output)
    record_property("install_s", seconds)
    after = board.snapshot()
    record_property("booted_slot_before", before["rauc_status"]["booted"])
    record_property("booted_slot", after["rauc_status"]["booted"])
    record_property("boot_variables", after["boot_variables"])
    record_property("commit", after["commit"])
    assert returncode != 0, (
        "INVALID CHECK, not an appliance failure: the install completed, so the cut did not land during it"
    )
    target = ({"A", "B"} - {before["rauc_status"]["booted"]}).pop()
    order, left = board.boot_variables()
    assert not (order[0] == target and left[target] > 0), (
        f"INVALID CHECK, not an appliance failure: slot {target} was activated, so the cut landed after "
        "the update was written, not while it was"
    )
    assert back_s is not None and back_s <= _POWER_CUT_BOUND_SECONDS, (
        f"back after {back_s} s (None: not within {Board.GIVE_UP_SECONDS} s of power returning); "
        f"bound {_POWER_CUT_BOUND_SECONDS} s; last read {last_read}"
    )
