"""A work directory under the repository's `build/`, which a script in the kas build container writes into."""

import contextlib
import shutil
import subprocess
import uuid
from pathlib import Path


class ContainerDir:
    """A fresh directory under `build/<name>/`, removed when the cleanup unwinds, that a container script writes into.

    The container sees the repository at `/work`, so it sees the directory at `/work/build/<name>/...`.

    Attributes:
        REPO: the repository root, from which `tools/kas-run.sh` runs.
        path: the directory on the host.
        container_path: the same directory, as the container sees it.
    """

    REPO = Path(__file__).resolve().parents[2]
    path: Path
    container_path: str

    def __init__(self, cleanup: contextlib.ExitStack, name: str) -> None:
        """Make the directory and register its removal.

        Args:
            cleanup: removes the directory when it unwinds.
            name: the directory under `build/` it is made in.
        """
        run = uuid.uuid4().hex
        self.path = self.REPO / "build" / name / run
        self.path.mkdir(parents=True)
        cleanup.callback(shutil.rmtree, self.path)
        self.container_path = f"/work/build/{name}/{run}"

    def run_script(self, script: str, *args: str) -> None:
        """Run `tests/target_suite/<script>` in the kas build container with `container_path` as its first argument.

        Args:
            script: the script's file name.
            *args: its further arguments.
        """
        words = " ".join((self.container_path, *args))
        subprocess.run(
            [
                str(self.REPO / "tools" / "kas-run.sh"),
                "shell",
                "kiosk-zero-w.yaml",
                "-c",
                f"bash /work/tests/target_suite/{script} {words}",
            ],
            cwd=self.REPO,
            check=True,
        )
