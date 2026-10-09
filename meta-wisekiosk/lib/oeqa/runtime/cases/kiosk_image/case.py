import subprocess
from pathlib import Path

from oeqa.runtime.case import OERuntimeTestCase

from . import verdict

UNIT_DIR = "usr/lib/systemd/system"
_DROPIN_DIRS = (UNIT_DIR, "etc/systemd/system")

DISPLAY_FILES = ("/srv/kiosk/index.html",)
_BINARY_PATHS = {name: f"/usr/bin/{name}" for name in verdict.REQUIRED_BINARIES}

# The repo root, resolved the same way kiosk_units/case.py resolves it (same
# nesting depth): cases/kiosk_image/case.py to the checkout's own root.
_REPO_ROOT = Path(__file__).resolve().parents[6]


def _debugfs(ext4_path, command):
    return subprocess.run(
        ["debugfs", "-R", command, str(ext4_path)], capture_output=True, text=True)


def _debugfs_present(ext4_path, path):
    """True if `stat <path>` resolves to a real inode (debugfs writes
    "File not found" to stderr and nothing to stdout otherwise)."""
    return bool(_debugfs(ext4_path, f"stat {path}").stdout.strip())


def _debugfs_cat(ext4_path, path):
    return _debugfs(ext4_path, f"cat {path}").stdout


def _debugfs_ls(ext4_path, dirpath):
    """Filenames of dirpath's own entries (excluding `.`/`..`); empty if
    dirpath does not exist."""
    names = []
    for line in _debugfs(ext4_path, f"ls -l {dirpath}").stdout.splitlines():
        parts = line.split()
        if parts and parts[-1] not in (".", ".."):
            names.append(parts[-1])
    return names


def _dropin_texts(ext4_path, unit_name):
    dir_names = {}
    for d in _DROPIN_DIRS:
        dropin_dir = f"{d}/{unit_name}.d"
        dir_names[dropin_dir] = _debugfs_ls(ext4_path, dropin_dir)
    return [_debugfs_cat(ext4_path, f"{dirpath}/{name}")
            for dirpath, name in verdict.dropin_order(dir_names)]


def _unit_text(ext4_path, unit_name):
    return _debugfs_cat(ext4_path, f"{UNIT_DIR}/{unit_name}")


class KioskImageTest(OERuntimeTestCase):
    """The image-content tier: one case, one method per check, over the
    build's own deployed `.ext4` -- no board, no network. Runs through
    `tools/oe-test.sh 127.0.0.1 kiosk_image.case` (docs/testing.md §"Running
    it"), never bitbake's own do_testimage task, so the datastore's own
    DEPLOY_DIR_IMAGE/TOPDIR (container paths, not host-real ones) are never
    read for the rootfs location: MACHINE plus this file's own on-disk
    location give the real path, the same arithmetic tools/oe-test.sh's own
    $DEPLOY already uses.
    """

    @classmethod
    def setUpClass(cls):
        machine = cls.td["MACHINE"]
        deploy_dir = _REPO_ROOT / "build" / f"tmp-{machine}" / "deploy" / "images" / machine
        KioskImageTest.ext4_path = deploy_dir / f"core-image-base-{machine}.rootfs.ext4"

        if not KioskImageTest.ext4_path.is_file():
            raise RuntimeError(f"no rootfs image at {KioskImageTest.ext4_path}")

    def test_execstart_flags(self):
        unit_text = _unit_text(KioskImageTest.ext4_path, "kiosk.service")
        dropins = _dropin_texts(KioskImageTest.ext4_path, "kiosk.service")
        outcome, reason = verdict.execstart_verdict(unit_text, dropins)
        if outcome != "ok":
            self.fail(reason)

    def test_display_files_present(self):
        present = {path for path in DISPLAY_FILES if _debugfs_present(KioskImageTest.ext4_path, path)}
        outcome, reason = verdict.path_presence_verdict(present, DISPLAY_FILES)
        if outcome != "ok":
            self.fail(reason)

    def test_required_binaries(self):
        present = {name for name, path in _BINARY_PATHS.items()
                   if _debugfs_present(KioskImageTest.ext4_path, path)}
        outcome, reason = verdict.path_presence_verdict(present, verdict.REQUIRED_BINARIES)
        if outcome != "ok":
            self.fail(reason)
