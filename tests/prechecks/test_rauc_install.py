"""Only tools/kiosk-install.sh runs `rauc install`."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN = r"rauc[[:space:]]+install"
EXCLUDED = (":!*.md", ":!tools/kiosk-install.sh", ":!tests/prechecks/")


def test_only_the_install_tool_runs_rauc_install() -> None:
    """No tracked non-Markdown file outside the install tool names the command on a non-comment line."""
    run = subprocess.run(
        ["git", "grep", "-nE", PATTERN, "--", *EXCLUDED],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode <= 1, f"git grep failed ({run.returncode}): {run.stderr}"
    hits = [
        line
        for line in run.stdout.splitlines()
        if not line.split(":", 2)[2].lstrip().startswith("#")
    ]
    assert not hits, "an install outside tools/kiosk-install.sh:\n" + "\n".join(hits)
