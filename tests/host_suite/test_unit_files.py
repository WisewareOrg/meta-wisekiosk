"""Host suite: constructed-input coverage of every function in unit_files.py.

check_image and resolve are exercised against a dict-backed fake image (lookup + read
callables), never against a real debugfs. parse_stat's fixtures are debugfs output
captured verbatim from the real built rootfs (and, for the slow-link case, from a
disposable seeded copy of it); debugfs_lookup/debugfs_read are exercised directly
against the real rootfs for the cases that rootfs actually has, and against a fake
debugfs (subprocess.run patched) for the slow-link case the rootfs has none of.
"""

import subprocess

import pytest

from unit_files import (
    UnitError,
    check_image,
    debugfs_lookup,
    debugfs_read,
    exec_argv0s,
    install_targets,
    parse,
    parse_stat,
    resolve,
    shipped_units,
)

# ---------------------------------------------------------------------------
# debugfs captures, verbatim.
#
# `debugfs -R "stat <path>" <image>` and `"cat <path>" <image>`, debugfs 1.47.2
# (1-Jan-2025), run read-only against
# build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/
# core-image-base-raspberrypi0-wifi.rootfs.ext4 (the same ROOTFS test_units.py and
# test_reproducibility.py use), except the slow-link pair, which has no example in
# that image (confirmed by a full debugfs `ls -l` walk of all 1076 directories: the
# longest real symlink target is 49 bytes) and was instead captured from a disposable
# copy of the same image, in scratch space, seeded with one `debugfs -w -R "symlink
# ..."` call and discarded afterward — never the original.
# ---------------------------------------------------------------------------

_BANNER = "debugfs 1.47.2 (1-Jan-2025)\n"

# A regular file: /usr/bin/measure-surf.sh
FILE_STAT_STDOUT = (
    "Inode: 1002   Type: regular    Mode:  0755   Flags: 0x80000\n"
    "Generation: 0    Version: 0x00000000:00000000\n"
    "User:     0   Group:     0   Project:     0   Size: 2693\n"
    "File ACL: 0\n"
    "Links: 1   Blockcount: 8\n"
    "Fragment:  Address: 0    Number: 0    Size: 0\n"
    " ctime: 0x6ae18617:00000000 -- Wed Oct 28 01:20:23 2026\n"
    " atime: 0x6ae1861e:00000000 -- Wed Oct 28 01:20:30 2026\n"
    " mtime: 0x5aa27f70:00000000 -- Fri Mar  9 07:34:56 2018\n"
    "crtime: 0x6ae18623:00000000 -- Wed Oct 28 01:20:35 2026\n"
    "Size of extra inode fields: 32\n"
    "Inode checksum: 0xbb51b430\n"
    "EXTENTS:\n"
    "(0):38618\n"
)
FILE_STAT_STDERR = _BANNER

# A directory: /usr/lib/systemd/system
DIR_STAT_STDOUT = (
    "Inode: 4192   Type: directory    Mode:  0755   Flags: 0x81000\n"
    "Generation: 0    Version: 0x00000000:00000000\n"
    "User:     0   Group:     0   Project:     0   Size: 16384\n"
    "File ACL: 0\n"
    "Links: 23   Blockcount: 32\n"
    "Fragment:  Address: 0    Number: 0    Size: 0\n"
    " ctime: 0x6ae18619:00000000 -- Wed Oct 28 01:20:25 2026\n"
    " atime: 0x6ae1861a:00000000 -- Wed Oct 28 01:20:26 2026\n"
    " mtime: 0x5aa27f70:00000000 -- Fri Mar  9 07:34:56 2018\n"
    "crtime: 0x6ae18626:00000000 -- Wed Oct 28 01:20:38 2026\n"
    "Size of extra inode fields: 32\n"
    "Inode checksum: 0x8e8d222e\n"
    "EXTENTS:\n"
    "(0):89424, (1):89550, (2-3):101923-101924\n"
)
DIR_STAT_STDERR = _BANNER

# A fast symlink: /etc/systemd/system/default.target -> /usr/lib/systemd/system/multi-user.target
FAST_SYMLINK_STAT_STDOUT = (
    "Inode: 610   Type: symlink    Mode:  0777   Flags: 0x0\n"
    "Generation: 0    Version: 0x00000000:00000000\n"
    "User:     0   Group:     0   Project:     0   Size: 41\n"
    "File ACL: 0\n"
    "Links: 1   Blockcount: 0\n"
    "Fragment:  Address: 0    Number: 0    Size: 0\n"
    " ctime: 0x6ae18619:00000000 -- Wed Oct 28 01:20:25 2026\n"
    " atime: 0x6ae1861a:00000000 -- Wed Oct 28 01:20:26 2026\n"
    " mtime: 0x5aa27f70:00000000 -- Fri Mar  9 07:34:56 2018\n"
    "crtime: 0x6ae18623:00000000 -- Wed Oct 28 01:20:35 2026\n"
    "Size of extra inode fields: 32\n"
    "Inode checksum: 0x92200f06\n"
    'Fast link dest: "/usr/lib/systemd/system/multi-user.target"\n'
)
FAST_SYMLINK_STAT_STDERR = _BANNER
FAST_SYMLINK_TARGET = "/usr/lib/systemd/system/multi-user.target"

# A missing path: /no/such/path/at/all
MISSING_STAT_STDOUT = ""
# Trailing space before the final newline is part of debugfs's own output; not a typo.
MISSING_STAT_STDERR = (
    "debugfs 1.47.2 (1-Jan-2025)\n"
    "/no/such/path/at/all: File not found by ext2_lookup \n"
)

# A slow symlink, > 60 byte target, captured from a disposable seeded copy of the
# real rootfs (the image itself has none): `debugfs -w -R "symlink
# /usr/lib/slow-link-test /usr/lib/this-is-a-deliberately-long-symlink-target-for-the-slow-link-test-case"`
# on the copy, confirmed landed with `stat` (Size: 79, no "Fast link dest:" line, an
# out-of-line EXTENTS block) before this capture, then discarded.
SLOW_SYMLINK_STAT_STDOUT = (
    "Inode: 7853   Type: symlink    Mode:  0777   Flags: 0x80000\n"
    "Generation: 0    Version: 0x00000000:00000000\n"
    "User:     0   Group:     0   Project:     0   Size: 79\n"
    "File ACL: 0\n"
    "Links: 1   Blockcount: 8\n"
    "Fragment:  Address: 0    Number: 0    Size: 0\n"
    " ctime: 0x6ae18c66:00000000 -- Wed Oct 28 01:47:18 2026\n"
    " atime: 0x6ae18c66:00000000 -- Wed Oct 28 01:47:18 2026\n"
    " mtime: 0x6ae18c66:00000000 -- Wed Oct 28 01:47:18 2026\n"
    "crtime: 0x6ae18c66:00000000 -- Wed Oct 28 01:47:18 2026\n"
    "Size of extra inode fields: 32\n"
    "Inode checksum: 0x4f83b39d\n"
    "EXTENTS:\n"
    "(0):101930\n"
)
SLOW_SYMLINK_STAT_STDERR = _BANNER
SLOW_SYMLINK_CAT_STDOUT = (
    "/usr/lib/this-is-a-deliberately-long-symlink-target-for-the-slow-link-test-case"
)
SLOW_SYMLINK_CAT_STDERR = _BANNER

ROOTFS = (
    "build/tmp-raspberrypi0-wifi/deploy/images/raspberrypi0-wifi/"
    "core-image-base-raspberrypi0-wifi.rootfs.ext4"
)


# ---------------------------------------------------------------------------
# A dict-backed fake image: check_image and resolve are tested against this, never
# against debugfs. `files`/`dirs`/`symlinks` are populated with every path component
# a test needs, parents included, so a component-walking implementation and a
# final-path-only implementation both see a consistent fake.
# ---------------------------------------------------------------------------


class FakeImage:
    def __init__(self):
        self._files: dict[str, str] = {}
        self._dirs: set[str] = {"/"}
        self._symlinks: dict[str, str] = {}

    def _add_parents(self, path):
        parts = path.strip("/").split("/")[:-1]
        built = ""
        for part in parts:
            built += "/" + part
            self._dirs.add(built)

    def add_file(self, path, content=""):
        self._add_parents(path)
        self._files[path] = content

    def add_dir(self, path):
        self._add_parents(path)
        self._dirs.add(path)

    def add_symlink(self, path, target):
        self._add_parents(path)
        self._symlinks[path] = target

    def lookup(self, path):
        if path in self._symlinks:
            return ("symlink", self._symlinks[path])
        if path in self._files:
            return ("file", None)
        if path in self._dirs:
            return ("dir", None)
        return None

    def read(self, path):
        return self._files.get(path)


# ---------------------------------------------------------------------------
# UnitError
# ---------------------------------------------------------------------------


def test_unit_error_is_an_exception():
    assert issubclass(UnitError, Exception)


# ---------------------------------------------------------------------------
# parse()
# ---------------------------------------------------------------------------


def test_parse_ignores_hash_and_semicolon_comments():
    text = "[Service]\n# a comment\nExecStart=/usr/bin/a\n; also a comment\n"
    assert parse(text)["Service"]["ExecStart"] == ["/usr/bin/a"]


def test_parse_joins_backslash_continuation():
    # The line break and the backslash that introduces it vanish; everything either
    # side of them is untouched, so a trailing space before "\" and no leading space
    # on the next line give an unambiguous joined result either way a continuation
    # algorithm is written.
    text = "[Service]\nExecStart=/usr/bin/foo \\\n--bar\n"
    assert parse(text)["Service"]["ExecStart"] == ["/usr/bin/foo --bar"]


def test_parse_accumulates_repeated_keys():
    text = "[Service]\nExecStart=/usr/bin/a\nExecStart=/usr/bin/b\n"
    assert parse(text)["Service"]["ExecStart"] == ["/usr/bin/a", "/usr/bin/b"]


def test_parse_empty_assignment_resets_the_list():
    text = (
        "[Service]\n"
        "ExecStart=/usr/bin/a\n"
        "ExecStart=/usr/bin/b\n"
        "ExecStart=\n"
        "ExecStart=/usr/bin/c\n"
    )
    assert parse(text)["Service"]["ExecStart"] == ["/usr/bin/c"]


# ---------------------------------------------------------------------------
# exec_argv0s()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prefix", ["@", "-", ":", "+", "!", "!!"])
def test_exec_argv0s_strips_each_prefix(prefix):
    text = f"[Service]\nExecStart={prefix}/usr/bin/true\n"
    assert exec_argv0s(text) == ["/usr/bin/true"]


def test_exec_argv0s_unquotes_a_quoted_argv0():
    text = '[Service]\nExecStart="/usr/local/my bin/thing" arg1\n'
    assert exec_argv0s(text) == ["/usr/local/my bin/thing"]


def test_exec_argv0s_sh_dash_c_argv0_is_sh_itself():
    text = "[Service]\nExecStart=/bin/sh -c 'echo hi'\n"
    assert exec_argv0s(text) == ["/bin/sh"]


def test_exec_argv0s_multiple_exec_start_lines():
    text = "[Service]\nExecStart=/usr/bin/a\nExecStart=/usr/bin/b\n"
    assert exec_argv0s(text) == ["/usr/bin/a", "/usr/bin/b"]


def test_exec_argv0s_empty_reset_drops_earlier_entries():
    text = (
        "[Service]\n"
        "ExecStart=/usr/bin/a\n"
        "ExecStart=\n"
        "ExecStart=/usr/bin/b\n"
    )
    assert exec_argv0s(text) == ["/usr/bin/b"]


def test_exec_argv0s_double_percent_is_a_literal_percent():
    text = "[Service]\nExecStart=/usr/bin/foo%%bar\n"
    assert exec_argv0s(text) == ["/usr/bin/foo%bar"]


def test_exec_argv0s_raises_on_a_percent_specifier():
    text = "[Service]\nExecStart=/usr/bin/foo%ibar\n"
    with pytest.raises(UnitError):
        exec_argv0s(text)


def test_exec_argv0s_raises_on_exec_search_path():
    text = "[Service]\nExecSearchPath=/custom/path\nExecStart=/usr/bin/true\n"
    with pytest.raises(UnitError):
        exec_argv0s(text)


def test_exec_argv0s_raises_on_a_lone_semicolon():
    text = "[Service]\nExecStart=;\n"
    with pytest.raises(UnitError):
        exec_argv0s(text)


# ---------------------------------------------------------------------------
# install_targets()
# ---------------------------------------------------------------------------


def test_install_targets_wanted_by():
    text = "[Install]\nWantedBy=multi-user.target\n"
    assert install_targets(text) == (["multi-user.target"], [])


def test_install_targets_required_by():
    text = "[Install]\nRequiredBy=some.target\n"
    assert install_targets(text) == ([], ["some.target"])


def test_install_targets_no_install_section():
    text = "[Service]\nExecStart=/usr/bin/true\n"
    assert install_targets(text) == ([], [])


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------


def test_resolve_bare_name_through_default_path():
    img = FakeImage()
    img.add_file("/usr/sbin/mybin")
    assert resolve("mybin", img.lookup) == "/usr/sbin/mybin"


def test_resolve_through_a_symlinked_directory():
    img = FakeImage()
    img.add_symlink("/opt/link", "/real")
    img.add_file("/real/mybin")
    assert resolve("/opt/link/mybin", img.lookup) == "/real/mybin"


def test_resolve_raises_on_relative_path_with_slash():
    img = FakeImage()
    with pytest.raises(UnitError):
        resolve("sub/dir/bin", img.lookup)


def test_resolve_missing_binary_returns_none():
    img = FakeImage()
    assert resolve("/usr/bin/doesnotexist", img.lookup) is None


def test_resolve_dangling_binary_symlink_returns_none():
    img = FakeImage()
    img.add_symlink("/opt/badlink", "/nonexistent-target")
    assert resolve("/opt/badlink", img.lookup) is None


def test_resolve_raises_on_a_symlink_loop():
    img = FakeImage()
    img.add_symlink("/opt/selfloop", "/opt/selfloop")
    with pytest.raises(UnitError):
        resolve("/opt/selfloop", img.lookup)


# ---------------------------------------------------------------------------
# parse_stat()
# ---------------------------------------------------------------------------


def test_parse_stat_regular_file():
    assert parse_stat(FILE_STAT_STDOUT, FILE_STAT_STDERR) == ("file", None)


def test_parse_stat_directory():
    assert parse_stat(DIR_STAT_STDOUT, DIR_STAT_STDERR) == ("dir", None)


def test_parse_stat_fast_symlink():
    result = parse_stat(FAST_SYMLINK_STAT_STDOUT, FAST_SYMLINK_STAT_STDERR)
    assert result == ("symlink", FAST_SYMLINK_TARGET)


def test_parse_stat_missing_path():
    assert parse_stat(MISSING_STAT_STDOUT, MISSING_STAT_STDERR) is None


def test_parse_stat_slow_symlink_target_is_none():
    # parse_stat alone cannot read a slow link's target (it isn't in stat output);
    # debugfs_lookup completes it with cat. See the next section.
    result = parse_stat(SLOW_SYMLINK_STAT_STDOUT, SLOW_SYMLINK_STAT_STDERR)
    assert result == ("symlink", None)


# ---------------------------------------------------------------------------
# debugfs_lookup() / debugfs_read()
#
# Exercised directly against the real built rootfs, for the cases it actually
# contains (file, directory, fast symlink, missing). The rootfs has no slow link to
# drive the cat-completion branch this way, so that one case instead stands in a fake
# debugfs (subprocess.run patched) fed the slow-link fixtures captured above.
# ---------------------------------------------------------------------------


def test_debugfs_lookup_regular_file():
    lookup = debugfs_lookup(ROOTFS)
    assert lookup("/usr/bin/measure-surf.sh") == ("file", None)


def test_debugfs_lookup_directory():
    lookup = debugfs_lookup(ROOTFS)
    assert lookup("/usr/lib/systemd/system") == ("dir", None)


def test_debugfs_lookup_fast_symlink():
    lookup = debugfs_lookup(ROOTFS)
    assert lookup("/etc/systemd/system/default.target") == ("symlink", FAST_SYMLINK_TARGET)


def test_debugfs_lookup_missing_path():
    lookup = debugfs_lookup(ROOTFS)
    assert lookup("/no/such/path/at/all") is None


def test_debugfs_lookup_slow_symlink_reads_target_via_cat(monkeypatch):
    # The real rootfs has no slow link (confirmed by the full ls -l walk cited above),
    # so the cat-completion branch is driven with the captured fixtures against a
    # stand-in debugfs, keyed on the stat/cat command debugfs_lookup issues.
    def fake_run(cmd, capture_output, text, check):
        command = cmd[2]
        if command.startswith("stat"):
            return subprocess.CompletedProcess(
                cmd, 0, SLOW_SYMLINK_STAT_STDOUT, SLOW_SYMLINK_STAT_STDERR
            )
        if command.startswith("cat"):
            return subprocess.CompletedProcess(
                cmd, 0, SLOW_SYMLINK_CAT_STDOUT, SLOW_SYMLINK_CAT_STDERR
            )
        raise AssertionError(f"unexpected debugfs command: {command!r}")

    monkeypatch.setattr("unit_files.subprocess.run", fake_run)
    lookup = debugfs_lookup("fake-image.ext4")
    assert lookup("/usr/lib/slow-link-test") == ("symlink", SLOW_SYMLINK_CAT_STDOUT)


def test_debugfs_read_regular_file():
    read = debugfs_read(ROOTFS)
    text = read("/usr/bin/measure-surf.sh")
    # Asserted on shape, not byte count: a size pin is a change detector that fails on
    # any edit to measure-surf.sh with no behavioural regression in debugfs_read.
    assert text is not None
    assert text.startswith("#!")


def test_debugfs_read_missing_path():
    read = debugfs_read(ROOTFS)
    assert read("/no/such/path/at/all") is None


# ---------------------------------------------------------------------------
# check_image()
#
# Each unit text below includes a real [Unit]/[Service]/[Install] shape; reason text
# is asserted only where the plan fixes it ("masked"), otherwise only the unit name
# and the (n) check number are asserted.
# ---------------------------------------------------------------------------


def test_check_image_empty_unit_list_is_vacuously_clean():
    img = FakeImage()
    assert check_image([], img.lookup, img.read) == []


def test_check_image_passes_a_clean_unit_with_no_install_section():
    img = FakeImage()
    img.add_file("/usr/bin/standalone-bin")
    img.add_file(
        "/usr/lib/systemd/system/standalone.service",
        "[Service]\nExecStart=/usr/bin/standalone-bin\n",
    )
    assert check_image(["standalone.service"], img.lookup, img.read) == []


def test_check_image_zero_exec_start_lines_passes_check_2():
    img = FakeImage()
    img.add_file(
        "/usr/lib/systemd/system/noexec.service",
        "[Service]\nType=oneshot\n",
    )
    assert check_image(["noexec.service"], img.lookup, img.read) == []


def test_check_image_a_timer_passes_check_2():
    img = FakeImage()
    img.add_file(
        "/usr/lib/systemd/system/sometimer.timer",
        "[Timer]\nOnBootSec=5min\n",
    )
    assert check_image(["sometimer.timer"], img.lookup, img.read) == []


def test_check_image_first_hit_wins_across_unit_dirs():
    img = FakeImage()
    # /etc copy is good; /usr/lib copy (lower priority) is broken. The broken copy
    # must never be read.
    img.add_file(
        "/etc/systemd/system/svc.service",
        "[Service]\nExecStart=/usr/bin/good-bin\n",
    )
    img.add_file("/usr/bin/good-bin")
    img.add_file(
        "/usr/lib/systemd/system/svc.service",
        "[Service]\nExecStart=/usr/bin/does-not-exist\n",
    )
    assert check_image(["svc.service"], img.lookup, img.read) == []


def test_check_image_missing_unit_file_is_check_1():
    img = FakeImage()
    result = check_image(["ghost.service"], img.lookup, img.read)
    assert len(result) == 1
    assert result[0].startswith("ghost.service: (1)")


def test_check_image_masked_unit_is_check_1_masked_exactly():
    img = FakeImage()
    img.add_symlink("/etc/systemd/system/masked.service", "/dev/null")
    assert check_image(["masked.service"], img.lookup, img.read) == [
        "masked.service: (1) masked"
    ]


def test_check_image_unresolvable_exec_start_is_check_2():
    img = FakeImage()
    img.add_file(
        "/usr/lib/systemd/system/broken.service",
        "[Service]\nExecStart=/usr/bin/doesnotexist\n",
    )
    result = check_image(["broken.service"], img.lookup, img.read)
    assert len(result) == 1
    assert result[0].startswith("broken.service: (2)")


def test_check_image_missing_enable_link_is_check_3():
    img = FakeImage()
    img.add_file("/usr/bin/good-bin")
    img.add_file(
        "/usr/lib/systemd/system/noenable.service",
        "[Service]\nExecStart=/usr/bin/good-bin\n\n[Install]\nWantedBy=multi-user.target\n",
    )
    result = check_image(["noenable.service"], img.lookup, img.read)
    assert len(result) == 1
    assert result[0].startswith("noenable.service: (3)")


def test_check_image_dangling_enable_link_passes_check_3_by_name_only():
    img = FakeImage()
    img.add_file("/usr/bin/good-bin")
    img.add_file(
        "/usr/lib/systemd/system/dangling-enable.service",
        "[Service]\nExecStart=/usr/bin/good-bin\n\n[Install]\nWantedBy=multi-user.target\n",
    )
    # The .wants entry exists by name only; its own target does not resolve. The
    # known limit: check (3) never follows it.
    img.add_symlink(
        "/etc/systemd/system/multi-user.target.wants/dangling-enable.service",
        "/nonexistent/target",
    )
    assert check_image(["dangling-enable.service"], img.lookup, img.read) == []


def test_check_image_enable_link_found_in_a_different_dir_than_the_unit_file():
    img = FakeImage()
    img.add_file("/usr/bin/good-bin")
    # Unit file is only in /usr/lib (lowest-priority hit); its enable link is only
    # under /etc, a different dir than the one the unit file was found in.
    img.add_file(
        "/usr/lib/systemd/system/cross-dir.service",
        "[Service]\nExecStart=/usr/bin/good-bin\n\n[Install]\nWantedBy=multi-user.target\n",
    )
    img.add_file("/etc/systemd/system/multi-user.target.wants/cross-dir.service")
    assert check_image(["cross-dir.service"], img.lookup, img.read) == []


def test_check_image_required_by_enable_link():
    img = FakeImage()
    img.add_file("/usr/bin/good-bin")
    img.add_file(
        "/usr/lib/systemd/system/req.service",
        "[Service]\nExecStart=/usr/bin/good-bin\n\n[Install]\nRequiredBy=some.target\n",
    )
    img.add_file("/usr/lib/systemd/system/some.target.requires/req.service")
    assert check_image(["req.service"], img.lookup, img.read) == []


def test_check_image_never_raises_unit_error_for_a_percent_specifier():
    img = FakeImage()
    img.add_file(
        "/usr/lib/systemd/system/pct.service",
        "[Service]\nExecStart=/usr/bin/foo%ibar\n",
    )
    result = check_image(["pct.service"], img.lookup, img.read)
    assert len(result) == 1
    assert result[0].startswith("pct.service: (2)")


def test_check_image_never_raises_unit_error_for_exec_search_path():
    img = FakeImage()
    img.add_file(
        "/usr/lib/systemd/system/searchpath.service",
        "[Service]\nExecSearchPath=/custom/path\nExecStart=/usr/bin/true\n",
    )
    result = check_image(["searchpath.service"], img.lookup, img.read)
    assert len(result) == 1
    assert result[0].startswith("searchpath.service: (2)")


def test_check_image_never_raises_unit_error_for_a_lone_semicolon():
    img = FakeImage()
    img.add_file(
        "/usr/lib/systemd/system/semicolon.service",
        "[Service]\nExecStart=;\n",
    )
    result = check_image(["semicolon.service"], img.lookup, img.read)
    assert len(result) == 1
    assert result[0].startswith("semicolon.service: (2)")


def test_check_image_never_raises_unit_error_for_an_exec_start_symlink_loop():
    img = FakeImage()
    img.add_symlink("/usr/bin/selfloop", "/usr/bin/selfloop")
    img.add_file(
        "/usr/lib/systemd/system/loopy.service",
        "[Service]\nExecStart=/usr/bin/selfloop\n",
    )
    result = check_image(["loopy.service"], img.lookup, img.read)
    assert len(result) == 1
    assert result[0].startswith("loopy.service: (2)")


# ---------------------------------------------------------------------------
# shipped_units()
#
# No parameters to construct around: it globs the real repo tree. Asserted on the glob
# mechanism's properties -- not today's exact fleet of units -- so a legitimate unit
# addition or retirement under recipes-* does not fail this test.
# ---------------------------------------------------------------------------


def test_shipped_units_globs_known_units_without_exempting_bootprofile():
    units = shipped_units()
    assert units
    assert all(name.endswith(".service") or name.endswith(".timer") for name in units)
    # Known units actually committed under recipes-* today.
    assert "wisekiosk.service" in units
    assert "kiosk-netcheck.service" in units
    # The boot profiler's unit moved to tests/diagnostics/, outside the glob by
    # location -- the plan's no-exemption mechanism, not a special case in the code.
    assert "kiosk-bootprofile.service" not in units
