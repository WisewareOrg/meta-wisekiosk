"""Target suite: image updates over the air, each starting with the board on the candidate and leaving it there.

The bundles are copies of the candidate, edited and re-signed by the operator key. Each carries an
install-check hook that refuses unless this run's nonce is in the board's `/tmp`.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from board import Board
from board.updates import Updates
from board_test import BoardTest
from candidate_bundles import CandidateBundles

# TST006's bound
_ON_PANEL_BOUND_SECONDS = 160
# stop polling; past the bound, so the record still carries the time it took
_ON_PANEL_GIVE_UP_SECONDS = 180
# TST003's bound
_POWER_CUT_BOUND_SECONDS = 60


@pytest.mark.sends_update
class TestImageUpdate(BoardTest):
    """An update installs, falls back when it cannot start or join, and survives a power cut while written."""

    def test_new_application_build(self, candidate_bundles: CandidateBundles) -> None:
        """TST006 new application build: install an update with a different build; time until it is on the panel.

        The clock starts as the restart is asked for, so it covers shutdown, boot and the page load.

        Args:
            candidate_bundles: this run's test bundles, and the candidate they were made from.
        """
        self.board.updates.return_to_candidate_after_test(candidate_bundles)
        self.record(requirement="TST006")
        page = self.board.app.page
        self.board.updates.assert_refused_then_install(
            candidate_bundles.new_build, candidate_bundles.nonce, self.record
        )

        started = self.board.restart_with("systemctl reboot")
        on_panel_s, _ = page.poll(
            until=lambda read: page.shows_instance(read.sample) and read.sample["stamp"] == candidate_bundles.stamp,
            within=_ON_PANEL_GIVE_UP_SECONDS,
            since=started,
        )

        self.record(on_panel_s=on_panel_s)
        assert on_panel_s is not None, (
            f"the new build was not on the panel within {_ON_PANEL_GIVE_UP_SECONDS} s; "
            f"last sample: {page.last_read.sample if page.last_read else None!r}"
        )
        assert on_panel_s <= _ON_PANEL_BOUND_SECONDS, (
            f"on the panel after {on_panel_s} s; TST006's bound is {_ON_PANEL_BOUND_SECONDS} s"
        )

    def test_cannot_start(self, candidate_bundles: CandidateBundles) -> None:
        """TST023 cannot start: install an update that cannot start; the board falls back, then takes a valid update.

        The fallback alone does not show why the update could not start; update_bundles.sh's
        `require_gone` checks are what show the bundle lacks init and sh.

        Args:
            candidate_bundles: this run's test bundles, and the candidate they were made from.
        """
        self.board.updates.return_to_candidate_after_test(candidate_bundles)
        self.record(requirement="TST023")

        self.board.updates.assert_falls_back_then_takes_candidate(
            candidate_bundles.cannot_start, candidate_bundles, count_boots=False, record=self.record
        )

    def test_cannot_reach_the_network(self, candidate_bundles: CandidateBundles) -> None:
        """TST024 cannot reach the network: install an update that starts but cannot join; the board falls back.

        Args:
            candidate_bundles: this run's test bundles, and the candidate they were made from.
        """
        self.board.updates.return_to_candidate_after_test(candidate_bundles)
        self.record(requirement="TST024")

        self.board.updates.assert_falls_back_then_takes_candidate(
            candidate_bundles.no_network, candidate_bundles, count_boots=True, record=self.record
        )

    def test_power_cut_during_an_update(self, candidate_bundles: CandidateBundles) -> None:
        """TST003 power cut during an image update: cut power once the update is being written into its slot.

        Installs the new-build bundle, which no slot already holds, and cuts once RAUC reports its copy
        step and the target slot's written-sector count has risen since the install began. Times from
        power returning until the page is served with the browser running.

        Args:
            candidate_bundles: this run's test bundles, and the candidate they were made from.
        """
        self.board.updates.return_to_candidate_after_test(candidate_bundles)
        self.record(requirement="TST003")
        updates = self.board.updates
        updates.allow_test_bundles(candidate_bundles.nonce)
        before = updates.next_boot_and_running_build()
        device = updates.other_slot_device(before["rauc_status"])
        idle = updates.install_progress(device)
        assert idle, f"could not read RAUC's progress or {device}'s write count"

        with ThreadPoolExecutor(max_workers=1) as pool:
            installing = pool.submit(
                updates.install_bundle, candidate_bundles.new_build, Updates.CANDIDATE_INSTALL_TIMEOUT_SECONDS
            )
            while True:
                assert not installing.done(), f"the install ended before it wrote to {device}: {installing.result()}"
                progress = updates.install_progress(device)
                if updates.is_copying(progress, since=idle.sectors_written):
                    break
                time.sleep(1)
            self.record(
                step_at_cut=progress.step, sectors_written_at_cut=progress.sectors_written - idle.sectors_written
            )
            on_began, on_command_s = self.board.cut_power()
            self.record(power_on_command_s=on_command_s)
            back_s, last_read = self.board.seconds_until_instance_up(since=on_began)
            returncode, output, seconds = installing.result()

        self.record(back_s=back_s, last_read=last_read, install_rc=returncode, install_output=output, install_s=seconds)
        after = updates.next_boot_and_running_build()
        self.record(
            booted_slot_before=before["rauc_status"]["booted"],
            booted_slot=after["rauc_status"]["booted"],
            boot_variables=after["boot_variables"],
            commit=after["commit"],
        )
        assert returncode != 0, (
            "INVALID CHECK, not an appliance failure: the install completed, so the cut did not land during it"
        )
        target = ({"A", "B"} - {before["rauc_status"]["booted"]}).pop()
        boot_order = self.board.boot_order()
        assert not (boot_order.order[0] == target and boot_order.attempts_left[target] > 0), (
            f"INVALID CHECK, not an appliance failure: slot {target} was activated, so the cut landed after "
            "the update was written, not while it was"
        )
        assert back_s is not None, (
            f"not back within {Board.GIVE_UP_SECONDS} s of power returning; last read: {last_read}"
        )
        assert back_s <= _POWER_CUT_BOUND_SECONDS, (
            f"back after {back_s} s; TST003's bound is {_POWER_CUT_BOUND_SECONDS} s"
        )
