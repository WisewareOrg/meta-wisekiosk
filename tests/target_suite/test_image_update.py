"""Target suite: image updates over the air, each with the board starting and ending on the candidate.

The bundles are copies of the candidate, edited and re-signed by the operator key. Each carries an
install-check hook that refuses unless this run's nonce is in the board's `/tmp`.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import NamedTuple

import pytest

from labgrid.driver.exception import ExecutionError

from panel import Panel
from updates import install, snapshot

_REPO = Path(__file__).resolve().parents[2]
_BUNDLES_SCRIPT = "/work/tests/target_suite/update_bundles.sh"
_PROBE = "/work/tests/target_suite/probe.js"
_NONCE_PATH = "/tmp/kiosk-update-nonce"
# a hang backstop, well past a slot's first adaptive install, which hashes the whole slot
_INSTALL_TIMEOUT_SECONDS = 1200
# 3 * (180 s boot wait + 180 s netcheck TimeoutStartSec + 30 s RebootWatchdogSec) + 180 s for the
# fallback boot; a backstop, the record carries the time it took
_FALLBACK_WAIT_SECONDS = 1350
# TST006's bound
_ON_PANEL_BOUND_SECONDS = 160
# stop polling; past the bound, so the record still carries the time it took
_ON_PANEL_GIVE_UP_SECONDS = 180

pytestmark = pytest.mark.sends_update


class UpdateBundles(NamedTuple):
    """The three test bundles, this run's nonce and stamp, and the candidate's bundle hash and path."""

    new_build: Path
    cannot_start: Path
    no_network: Path
    nonce: str
    stamp: str
    hash: str
    candidate: Path


@pytest.fixture(scope="module")
def update_bundles(request, bench_candidate):
    """Build the three test bundles in the host's `/tmp` through `tools/kas-run.sh`.

    Skips outside a build, where there is no candidate bundle to copy.
    """
    if bench_candidate is None:
        pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
    run_dir = tempfile.mkdtemp(prefix="kiosk-update-bundles-", dir="/tmp")
    request.addfinalizer(lambda: shutil.rmtree(run_dir))
    nonce = uuid.uuid4().hex
    stamp = uuid.uuid4().hex
    subprocess.run(
        [
            str(_REPO / "tools" / "kas-run.sh"),
            "shell",
            "kiosk-zero-w.yaml",
            "-c",
            f"bash {_BUNDLES_SCRIPT} {run_dir} {nonce} {stamp} {_PROBE}",
        ],
        cwd=_REPO,
        env={**os.environ, "KAS_RUN_TMP_DIR": run_dir},
        check=True,
    )
    candidate_hash = (Path(run_dir) / "candidate.hash").read_text().strip()
    candidate = _REPO / (Path(run_dir) / "candidate.path").read_text().strip()
    return UpdateBundles(
        Path(run_dir) / "new-build.raucb",
        Path(run_dir) / "cannot-start.raucb",
        Path(run_dir) / "no-network.raucb",
        nonce,
        stamp,
        candidate_hash,
        candidate,
    )


def _booted_slot(rauc_status):
    """The booted slot's name and the hash of the bundle it was installed from."""
    for entry in rauc_status["slots"]:
        for name, slot in entry.items():
            if slot["state"] == "booted":
                return name, slot["slot_status"]["bundle"]["hash"]
    raise AssertionError(f"no booted slot in rauc status: {rauc_status!r}")




def _boot_ids(board):
    """The set of boot ids in the board's journal."""
    stdout = board.run("journalctl --list-boots -o json", check=True, timeout=None)[0]
    return {boot["boot_id"] for boot in json.loads("\n".join(stdout))}


@pytest.fixture
def back_on_candidate(request, board, update_bundles):
    """At teardown, put the board back on the candidate unless it runs it and will boot it next."""

    def restore():
        rauc_status = snapshot(board)["rauc_status"]
        _slot, booted_hash = _booted_slot(rauc_status)
        order, _left = board.boot_variables()
        if booted_hash == update_bundles.hash and order[0] == rauc_status["booted"]:
            return
        returncode, output, _seconds = install(
            request, board, update_bundles.candidate, _INSTALL_TIMEOUT_SECONDS
        )
        assert returncode == 0, f"reinstalling the candidate returned {returncode}: {output}"
        board.restart_by("systemctl reboot")

    request.addfinalizer(restore)


def _refuse_then_install(request, board, bundle, update_bundles, record_property):
    """Offer `bundle` without the nonce and assert the refusal, then install it with the nonce.

    Returns:
        dict: the board's `snapshot` from before the install.
    """
    board.run(f"rm -f {_NONCE_PATH}", check=True)
    before = snapshot(board)
    returncode, output, _seconds = install(request, board, bundle, _INSTALL_TIMEOUT_SECONDS)
    assert returncode == 1, f"the bundle without the nonce returned {returncode}, not a refusal (1): {output}"
    for reason in ("Bundle rejected", "test bundle: no run nonce"):
        assert reason in output, f"refused, but not for the reason {reason!r}: {output}"
    assert snapshot(board) == before, "the board changed when it refused the bundle"

    board.run(f"printf %s {update_bundles.nonce} > {_NONCE_PATH}", check=True)
    request.addfinalizer(lambda: board.run(f"rm -f {_NONCE_PATH}", check=True))
    before = snapshot(board)
    returncode, output, seconds = install(request, board, bundle, _INSTALL_TIMEOUT_SECONDS)
    record_property("install_rc", returncode)
    record_property("install_output", output)
    record_property("install_s", seconds)
    assert returncode == 0, f"the install returned {returncode}: {output}"
    assert snapshot(board)["boot_id"] == before["boot_id"], "the board restarted during the install"
    return before


def _fall_back_and_accept(
    request, board, bench_candidate, update_bundles, record_property, bundle, count_boots
):
    """Install `bundle`, restart into it, and assert the board falls back and takes the candidate.

    Args:
        count_boots (bool): also assert that the journal holds one new boot per failed attempt.
    """
    before = _refuse_then_install(request, board, bundle, update_bundles, record_property)
    target = ({"A", "B"} - {before["rauc_status"]["booted"]}).pop()
    order, left = board.boot_variables()
    assert order[0] == target, f"the update's slot {target} does not lead BOOT_ORDER: {order}"
    attempts = left[target]
    record_property("attempts", attempts)
    assert 0 < attempts <= 3, f"slot {target} has {attempts} attempts left, not 1 to 3"
    boots_before = _boot_ids(board) if count_boots else None

    started = time.monotonic()
    board.restart_by("systemctl reboot", wait_seconds=_FALLBACK_WAIT_SECONDS)
    back_s = round(time.monotonic() - started, 1)
    record_property("back_s", back_s)

    after = snapshot(board)
    assert _booted_slot(after["rauc_status"]) == _booted_slot(before["rauc_status"]), (
        "the board is not back on the previous slot and bundle"
    )
    assert after["commit"] == before["commit"], "the board is not back on the previous build"
    order, left = board.boot_variables()
    assert order[0] == target, f"the update's slot {target} no longer leads BOOT_ORDER: {order}"
    assert left[target] == 0, f"slot {target} has {left[target]} attempts left, not 0"
    if count_boots:
        # journalctl lists boot ids without the dashes /proc/sys/kernel/random/boot_id has
        failed = _boot_ids(board) - boots_before - {after["boot_id"].replace("-", "")}
        assert len(failed) == attempts, (
            f"{len(failed)} failed boots in the journal, expected {attempts}: the update did not start "
            "and fail to reach the network the way the test means"
        )

    returncode, output, _seconds = install(
        request, board, update_bundles.candidate, _INSTALL_TIMEOUT_SECONDS
    )
    assert returncode == 0, f"installing the candidate returned {returncode}: {output}"
    board.restart_by("systemctl reboot")
    _slot, booted_hash = _booted_slot(snapshot(board)["rauc_status"])
    assert booted_hash == update_bundles.hash, "the board is not on the candidate's bundle"
    assert board.commit() == bench_candidate, "the board is not on the candidate's build"


def test_new_application_build(
    request, board, update_bundles, back_on_candidate, record_property
):
    """TST006 new application build: install an update with a different build; time until it is on the panel.

    The clock starts as the restart is asked for, so it covers shutdown, boot and the page load.
    """
    record_property("requirement", "TST006")
    _refuse_then_install(request, board, update_bundles.new_build, update_bundles, record_property)

    started = time.monotonic()
    board.restart_by("systemctl reboot")
    panel = Panel(board)
    sample = None
    on_panel_s = None
    while time.monotonic() - started <= _ON_PANEL_GIVE_UP_SECONDS:
        try:
            _uptime_s, sample = panel.read()
        except (ExecutionError, subprocess.TimeoutExpired):
            sample = None
        if panel.on_panel(sample) and sample["stamp"] == update_bundles.stamp:
            on_panel_s = round(time.monotonic() - started, 1)
            break
        time.sleep(1)
    record_property("on_panel_s", on_panel_s)
    assert on_panel_s is not None, (
        f"the new build was not on the panel within {_ON_PANEL_GIVE_UP_SECONDS} s; last sample: {sample!r}"
    )
    assert on_panel_s <= _ON_PANEL_BOUND_SECONDS, (
        f"on the panel after {on_panel_s} s; TST006's bound is {_ON_PANEL_BOUND_SECONDS} s"
    )


def test_cannot_start(
    request, board, bench_candidate, update_bundles, back_on_candidate, record_property
):
    """TST023 cannot start: install an update that cannot start; the board falls back, then takes a valid update.

    The fallback alone does not show why the update could not start; update_bundles.sh's
    `require_gone` checks are what show the bundle lacks init and sh.
    """
    record_property("requirement", "TST023")
    _fall_back_and_accept(
        request,
        board,
        bench_candidate,
        update_bundles,
        record_property,
        update_bundles.cannot_start,
        count_boots=False,
    )


def test_cannot_reach_the_network(
    request, board, bench_candidate, update_bundles, back_on_candidate, record_property
):
    """TST024 cannot reach the network: install an update that starts but cannot join; the board falls back."""
    record_property("requirement", "TST024")
    _fall_back_and_accept(
        request,
        board,
        bench_candidate,
        update_bundles,
        record_property,
        update_bundles.no_network,
        count_boots=True,
    )
