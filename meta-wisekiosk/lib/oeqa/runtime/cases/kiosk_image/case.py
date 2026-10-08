import hashlib
import subprocess
import tempfile
from pathlib import Path

from framework.base import ImageCase

from . import verdict

UNIT_DIR = "usr/lib/systemd/system"
# etc overrides a usr/lib drop-in, so its texts are appended last (systemd's
# own precedence); no real drop-in ships in either directory on this image
# today.
_DROPIN_DIRS = (UNIT_DIR, "etc/systemd/system")

# The display's own served entry point, and the binaries the verification
# tier's own checks need -- both read from the deployed .ext4 directly
# ("so the image checked is the image that ships"), via debugfs, never the
# pre-image WORKDIR rootfs directory.
DISPLAY_FILES = ("/srv/kiosk/index.html",)
_BINARY_PATHS = {name: f"/usr/bin/{name}" for name in verdict.REQUIRED_BINARIES}


def _dropin_texts(rootfs_dir, unit_name):
    texts = []
    for d in _DROPIN_DIRS:
        dropin_dir = rootfs_dir / d / f"{unit_name}.d"
        if dropin_dir.is_dir():
            texts.extend(p.read_text() for p in sorted(dropin_dir.glob("*.conf")))
    return texts


def _unit_text(rootfs_dir, unit_name):
    return (rootfs_dir / UNIT_DIR / unit_name).read_text()


def _debugfs_present(ext4_path, path):
    """True if `debugfs -R "stat <path>" <ext4_path>` resolves to a real
    inode. debugfs writes "File not found" to stderr and nothing to
    stdout for an absent path, and prints the inode block (without
    following a symlink) for one that exists -- the real shape, confirmed
    directly against this build's own .ext4 for a regular file, a
    symlink, and an absent path."""
    result = subprocess.run(
        ["debugfs", "-R", f"stat {path}", str(ext4_path)],
        capture_output=True, text=True)
    return bool(result.stdout.strip())


class KioskImageTest(ImageCase):
    """The image-content tier (#206, reduced to the appliance's own needs
    -- the owner's lens, ~/.claude/plans/202/step4/brief.md "Subject and
    size"): one case, one method per check, over the build's own rootfs
    and bundle -- no board, no network. Every parse and judgement is
    verdict.py's own; this class only collects inputs and asserts on what
    came back. systemd-analyze verify runs on the board instead
    (cases/kiosk_units), the appliance's own systemd validating its own
    units, not a host-side artefact read."""

    # -- the image starts the kiosk display as designed (SRS008/TST008) ----

    def test_execstart_flags(self):
        unit_text = _unit_text(ImageCase.rootfs_dir, "kiosk.service")
        dropins = _dropin_texts(ImageCase.rootfs_dir, "kiosk.service")
        outcome, reason = verdict.execstart_verdict(unit_text, dropins)
        if outcome != "ok":
            self.fail(reason)

    # -- what was verified is what ships (SRS009/TST009) --------------------

    def test_bundle_image_tie(self):
        manifest_text = self._bundle_manifest_text()
        ext4_sha256 = self._ext4_sha256()
        outcome, reason = verdict.bundle_image_hash_verdict(manifest_text, ext4_sha256)
        if outcome != "ok":
            self.fail(reason)

    def test_display_files_present(self):
        present = {path for path in DISPLAY_FILES if _debugfs_present(ImageCase.ext4_path, path)}
        outcome, reason = verdict.path_presence_verdict(present, DISPLAY_FILES)
        if outcome != "ok":
            self.fail(reason)

    # -- the verification tier's own precondition (a guard, no SRS/TST item) -

    def test_required_binaries(self):
        present = {name for name, path in _BINARY_PATHS.items()
                   if _debugfs_present(ImageCase.ext4_path, path)}
        outcome, reason = verdict.path_presence_verdict(present, verdict.REQUIRED_BINARIES)
        if outcome != "ok":
            self.fail(reason)

    @staticmethod
    def _ext4_sha256():
        digest = hashlib.sha256()
        with open(ImageCase.ext4_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _bundle_manifest_text():
        # The bundle is plain squashfs with an appended RAUC signature;
        # unsquashfs reads from the front and needs no key to extract one
        # named file -- no rauc-native sysroot exists anywhere in this
        # tree for the design's first-named `rauc info` mechanism
        # (impl-notes.md "Interfaces").
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "bundle"
            subprocess.run(
                ["unsquashfs", "-d", str(out_dir), "-f", str(ImageCase.bundle_path), "manifest.raucm"],
                capture_output=True, text=True, check=True)
            return (out_dir / "manifest.raucm").read_text()
