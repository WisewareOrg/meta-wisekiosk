"""The image updates the image-update tests offer: copies of the candidate's bundle, edited and re-signed."""

import contextlib
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import NamedTuple

import pytest

_REPO = Path(__file__).resolve().parents[2]
_BUNDLES_SCRIPT = "/work/tests/target_suite/update_bundles.sh"
_PROBE = "/work/tests/target_suite/probe.js"


class CandidateBundles(NamedTuple):
    """The three test bundles, this run's nonce, and the candidate they were made from.

    Attributes:
        new_build: a bundle whose page carries a stamp of this run's.
        cannot_start: a bundle whose image cannot start.
        no_network: a bundle whose image starts but cannot join the network.
        nonce: what the board's `/tmp` must hold for a test bundle's install-check hook to accept it.
        hash: the candidate bundle's hash, as RAUC records it for the slot it installs.
        candidate: the candidate's own bundle on the host.
    """

    new_build: Path
    cannot_start: Path
    no_network: Path
    nonce: str
    hash: str
    candidate: Path

    @classmethod
    def build(cls, cleanup: contextlib.ExitStack, bench_candidate: str | None) -> "CandidateBundles":
        """Build the three test bundles in a `/tmp` run directory through `tools/kas-run.sh`.

        Skips the test outside a build, where there is no candidate bundle to copy.

        Args:
            cleanup: removes the run directory when it unwinds.
            bench_candidate: the commit under test, or None outside a build.

        Returns:
            The bundles.
        """
        if bench_candidate is None:
            pytest.skip("no bench_candidate: a plain pytest run, or bench test --skip-build")
        run_dir = Path(tempfile.mkdtemp(prefix="kiosk-update-bundles-", dir="/tmp"))
        cleanup.callback(shutil.rmtree, run_dir)
        nonce = uuid.uuid4().hex
        # what the new-build bundle's page carries, which makes it a different build from the candidate
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
            env={**os.environ, "KAS_RUN_TMP_DIR": str(run_dir)},
            check=True,
        )
        return cls(
            run_dir / "new-build.raucb",
            run_dir / "cannot-start.raucb",
            run_dir / "no-network.raucb",
            nonce,
            (run_dir / "candidate.hash").read_text().strip(),
            _REPO / (run_dir / "candidate.path").read_text().strip(),
        )
