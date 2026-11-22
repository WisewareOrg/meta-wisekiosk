"""A scratch directory in `/tmp` that a script run in the kas build container fills."""

import contextlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class ContainerDir:
    """A fresh directory in `/tmp`, removed when the cleanup unwinds, that a container script writes into.

    Attributes:
        REPO: the repository root, from which `tools/kas-run.sh` runs.
        path: the directory; `run` mounts it at the same path in the container.
    """

    REPO = Path(__file__).resolve().parents[2]
    path: Path

    def __init__(self, cleanup: contextlib.ExitStack) -> None:
        """Make the directory and register its removal.

        Args:
            cleanup: removes the directory when it unwinds.
        """
        self.path = Path(tempfile.mkdtemp(prefix="kiosk-test-", dir="/tmp"))
        cleanup.callback(shutil.rmtree, self.path)

    def run(self, script: str, *args: str) -> None:
        """Run `tests/target_suite/<script>` in the kas build container with `path` as its first argument.

        Args:
            script: the script's file name.
            *args: its further arguments.
        """
        words = " ".join((str(self.path), *args))
        subprocess.run(
            [
                str(self.REPO / "tools" / "kas-run.sh"),
                "shell",
                "kiosk-zero-w.yaml",
                "-c",
                f"bash /work/tests/target_suite/{script} {words}",
            ],
            cwd=self.REPO,
            env={**os.environ, "KAS_RUN_TMP_DIR": str(self.path)},
            check=True,
        )
