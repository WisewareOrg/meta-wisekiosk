#!/usr/bin/env python3
"""Self-test for tools/app-lockfile.py. Run by `just guards` and by CI.

    app-lockfile-test.py        -- every case

`app-lockfile.py` writes the app's npm shrinkwrap by fetching its own
frontend/package-lock.json straight from the pinned commit, never running npm,
and skips the fetch entirely once a gitignored `<shrinkwrap>.srcrev` stamp
beside it already names the current pin. Importable seams: `_src_inc_fields
(src_inc)` parses the pin and clone URL from a path handed to it (a fixture
here); `fetch_lockfile(url, srcrev)` is the only network-touching call,
stubbed here by replacing `urllib.request.urlopen` for the call's duration --
never a real fetch; `is_current(srcrev, path)` and `write_shrinkwrap(content,
srcrev, path)` take the shrinkwrap path as a parameter (a fixture here,
SHRINKWRAP_PATH in production). No case here ever touches the real
wisekiosk-src.inc or writes into the real repo tree.
"""
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app_lockfile = load("app-lockfile")

PASS, FAIL = [], []


def case(name, got, want):
    (PASS if got == want else FAIL).append(name)
    if got != want:
        print(f"FAIL  {name}\n        want {want!r}\n        got  {got!r}")


SRCREV = "a" * 40


def write_src_inc(path, srcrev=SRCREV,
                   url="git://github.com/example-org/WiseKiosk.git;protocol=https"):
    """A fixture wisekiosk-src.inc, in the same field order tools/go-mods.py's
    own copy of this parse expects."""
    path.write_text(f'SRCREV = "{srcrev}"\nSRC_URI = "{url}"\n')


# --- _src_inc_fields: SRCREV + URL parsed from a fixture .inc --------------

def src_inc_cases():
    with tempfile.TemporaryDirectory() as tmp:
        src_inc = Path(tmp) / "wisekiosk-src.inc"
        write_src_inc(src_inc)
        url, srcrev = app_lockfile._src_inc_fields(src_inc)
    case("_src_inc_fields: the pinned commit",
         srcrev, SRCREV)
    case("_src_inc_fields: the clone URL, protocol taken from `;protocol=`",
         url, "https://github.com/example-org/WiseKiosk.git")

    # Spelled differently but valid: no `;protocol=` param at all defaults to
    # https, same as tools/go-mods.py's own parse of this field.
    with tempfile.TemporaryDirectory() as tmp:
        src_inc = Path(tmp) / "wisekiosk-src.inc"
        write_src_inc(src_inc,
                      url="git://github.com/example-org/WiseKiosk.git")
        url, _ = app_lockfile._src_inc_fields(src_inc)
    case("_src_inc_fields: no protocol param defaults to https",
         url, "https://github.com/example-org/WiseKiosk.git")


# --- _raw_url: the raw.githubusercontent.com URL for one sha ---------------

def raw_url_cases():
    case("_raw_url: a github clone URL, no .git suffix",
         app_lockfile._raw_url(
             "https://github.com/example-org/WiseKiosk", SRCREV),
         f"https://raw.githubusercontent.com/example-org/WiseKiosk/"
         f"{SRCREV}/frontend/package-lock.json")
    # Spelled differently but valid: the .git suffix wisekiosk-src.inc's own
    # clone URL actually carries must come off, or the raw URL 404s.
    case("_raw_url: a .git suffix is stripped",
         app_lockfile._raw_url(
             "https://github.com/example-org/WiseKiosk.git", SRCREV),
         f"https://raw.githubusercontent.com/example-org/WiseKiosk/"
         f"{SRCREV}/frontend/package-lock.json")
    # Must-not-fire: a non-github.com URL is refused outright, not
    # mis-rendered into a URL that silently 404s at fetch time.
    try:
        app_lockfile._raw_url("https://example.invalid/WiseKiosk.git", SRCREV)
        raised = None
    except ValueError as exc:
        raised = exc
    case("_raw_url: a non-github.com URL raises rather than guessing",
         raised is not None, True)


# --- fetch_lockfile: the only network call, stubbed at urlopen -------------

class FakeResponse:
    """What `with urllib.request.urlopen(...) as response: response.read()`
    needs -- nothing else, matching fetch_lockfile's own usage exactly."""

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.data


def fetch_lockfile_cases():
    url = "https://github.com/example-org/WiseKiosk"
    payload = b'{"lockfileVersion": 3, "packages": {}}'
    expected_raw_url = (
        f"https://raw.githubusercontent.com/example-org/WiseKiosk/"
        f"{SRCREV}/frontend/package-lock.json")

    seen = {}

    def ok_urlopen(requested_url):
        seen["url"] = requested_url
        return FakeResponse(payload)

    was = urllib.request.urlopen
    urllib.request.urlopen = ok_urlopen
    try:
        got = app_lockfile.fetch_lockfile(url, SRCREV)
    finally:
        urllib.request.urlopen = was
    case("fetch_lockfile: requests the raw URL for the pinned commit",
         seen.get("url"), expected_raw_url)
    case("fetch_lockfile: returns the response body verbatim", got, payload)

    # THE case: an HTTP error refuses (exit 2) rather than raising an
    # unhandled exception or returning a truncated/empty body as if it were
    # the lockfile.
    def failing_urlopen(requested_url):
        raise urllib.error.HTTPError(requested_url, 404, "Not Found", None, None)

    was = urllib.request.urlopen
    urllib.request.urlopen = failing_urlopen
    stderr = io.StringIO()
    code = None
    try:
        with contextlib.redirect_stderr(stderr):
            try:
                app_lockfile.fetch_lockfile(url, SRCREV)
            except SystemExit as exc:
                code = exc.code
    finally:
        urllib.request.urlopen = was
    case("fetch_lockfile: an HTTP error refuses rather than raising",
         code, 2)
    case("fetch_lockfile: the refusal names the HTTP status",
         "404" in stderr.getvalue(), True)
    # And main()'s own composition -- `content = fetch_lockfile(...)` before
    # `write_shrinkwrap(content)` -- means a call that never returns can
    # never reach write_shrinkwrap: there is no content for it to write.
    # write_shrinkwrap_cases below covers write_shrinkwrap's own no-write
    # refusal directly; nothing here needs to reach the real SHRINKWRAP_PATH
    # to prove an HTTP error leaves no file behind.


# --- stamp_path_for / is_current: the "already current" seam ---------------

def stamp_path_for_cases():
    case("stamp_path_for: <name> becomes <name>.srcrev, beside the target",
         app_lockfile.stamp_path_for(Path("/x/npm-shrinkwrap.json")),
         Path("/x/npm-shrinkwrap.json.srcrev"))


def is_current_cases():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "npm-shrinkwrap.json"
        target.write_bytes(b"{}")
        app_lockfile.stamp_path_for(target).write_text(SRCREV)
        case("is_current: file and matching stamp both present",
             app_lockfile.is_current(SRCREV, path=target), True)

    # Must-not-fire, three ways: a matching stamp with no file, a file with
    # no stamp, and a stamp naming a different commit -- none of these is
    # "current", or a half-seeded fixture or a stale pin would be trusted.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "npm-shrinkwrap.json"
        app_lockfile.stamp_path_for(target).write_text(SRCREV)
        case("is_current: a stamp with no shrinkwrap file is not current",
             app_lockfile.is_current(SRCREV, path=target), False)

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "npm-shrinkwrap.json"
        target.write_bytes(b"{}")
        case("is_current: a shrinkwrap with no stamp is not current",
             app_lockfile.is_current(SRCREV, path=target), False)

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "npm-shrinkwrap.json"
        target.write_bytes(b"{}")
        app_lockfile.stamp_path_for(target).write_text("f" * 40)
        case("is_current: a stamp naming a different commit is not current",
             app_lockfile.is_current(SRCREV, path=target), False)


# --- write_shrinkwrap: validate, write atomically, then stamp --------------

def write_shrinkwrap_cases():
    payload = b'{"lockfileVersion": 3, "packages": {}}'

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "npm-shrinkwrap.json"
        rc = app_lockfile.write_shrinkwrap(payload, SRCREV, path=target)
        case("write_shrinkwrap: valid JSON returns 0", rc, 0)
        case("write_shrinkwrap: bytes are written verbatim",
             target.read_bytes(), payload)
        case("write_shrinkwrap: stamps the file with the given srcrev",
             app_lockfile.stamp_path_for(target).read_text(), SRCREV)
        case("write_shrinkwrap: is_current agrees once written",
             app_lockfile.is_current(SRCREV, path=target), True)

    # THE case: invalid JSON refuses and leaves no file and no stamp at all,
    # rather than a zero-byte or partial shrinkwrap -- or a stamp claiming a
    # file that was never written -- an operator's build would then trust.
    with tempfile.TemporaryDirectory() as tmp, \
         contextlib.redirect_stderr(io.StringIO()):
        target = Path(tmp) / "npm-shrinkwrap.json"
        rc = app_lockfile.write_shrinkwrap(b"not json at all", SRCREV, path=target)
        case("write_shrinkwrap: invalid JSON refuses (non-zero)", rc != 0, True)
        case("write_shrinkwrap: invalid JSON leaves no file behind",
             target.exists(), False)
        case("write_shrinkwrap: invalid JSON leaves no stamp behind",
             app_lockfile.stamp_path_for(target).exists(), False)

    # Must-not-fire: a refusal happens before write_shrinkwrap ever attempts
    # a write (JSON validation runs first), so an existing file -- and its
    # stamp -- are left alone.
    with tempfile.TemporaryDirectory() as tmp, \
         contextlib.redirect_stderr(io.StringIO()):
        target = Path(tmp) / "npm-shrinkwrap.json"
        target.write_bytes(payload)
        app_lockfile.stamp_path_for(target).write_text(SRCREV)
        app_lockfile.write_shrinkwrap(b"not json at all", "f" * 40, path=target)
        case("write_shrinkwrap: a refusal leaves an existing file untouched",
             target.read_bytes(), payload)
        case("write_shrinkwrap: a refusal leaves an existing stamp untouched",
             app_lockfile.stamp_path_for(target).read_text(), SRCREV)

    # THE atomic-write case: an interrupted replace must leave the original
    # file exactly as it was and no `.tmp` sibling behind -- the write is
    # tmp-file-then-os.replace precisely so a crash mid-write cannot leave a
    # half-written shrinkwrap in place. The old stamp is unlinked BEFORE the
    # replace, not after, so an interruption here is expected to remove it --
    # a missing stamp reads as stale, but a stamp naming content that was
    # never written would read as current for the WRONG file.
    with tempfile.TemporaryDirectory() as tmp, \
         contextlib.redirect_stderr(io.StringIO()):
        target = Path(tmp) / "npm-shrinkwrap.json"
        target.write_bytes(payload)
        app_lockfile.stamp_path_for(target).write_text(SRCREV)

        was_replace = os.replace

        def failing_replace(*a, **kw):
            raise OSError("simulated crash mid-replace")

        os.replace = failing_replace
        try:
            try:
                app_lockfile.write_shrinkwrap(
                    b'{"lockfileVersion": 3, "packages": {"new": 1}}',
                    "f" * 40, path=target)
                raised = False
            except OSError:
                raised = True
        finally:
            os.replace = was_replace

        case("write_shrinkwrap: an interrupted replace propagates, "
             "not silently swallowed", raised, True)
        case("write_shrinkwrap: an interrupted replace leaves the original "
             "file byte-unchanged", target.read_bytes(), payload)
        case("write_shrinkwrap: an interrupted replace leaves no stamp "
             "(unlinked before the replace)",
             app_lockfile.stamp_path_for(target).exists(), False)
        case("write_shrinkwrap: an interrupted replace leaves no .tmp "
             "sibling behind",
             list(Path(tmp).glob("*.tmp")), [])

    # A second failure point: the replace itself succeeds but the stamp
    # write after it fails. The shrinkwrap now holds the NEW content with no
    # stamp at all -- the safe failure mode, since a stamp naming the OLD
    # srcrev next to NEW content would read as current for a commit whose
    # content was never actually written.
    with tempfile.TemporaryDirectory() as tmp, \
         contextlib.redirect_stderr(io.StringIO()):
        target = Path(tmp) / "npm-shrinkwrap.json"
        target.write_bytes(payload)
        app_lockfile.stamp_path_for(target).write_text(SRCREV)
        new_payload = b'{"lockfileVersion": 3, "packages": {"new": 1}}'

        stamp_path = app_lockfile.stamp_path_for(target)
        was_write_text = Path.write_text

        def failing_write_text(self, *a, **kw):
            if self == stamp_path:
                raise OSError("simulated crash writing the stamp")
            return was_write_text(self, *a, **kw)

        Path.write_text = failing_write_text
        try:
            try:
                app_lockfile.write_shrinkwrap(new_payload, "f" * 40, path=target)
                raised = False
            except OSError:
                raised = True
        finally:
            Path.write_text = was_write_text

        case("write_shrinkwrap: a stamp-write failure after a successful "
             "replace still propagates", raised, True)
        case("write_shrinkwrap: a stamp-write failure still leaves the new "
             "content written", target.read_bytes(), new_payload)
        case("write_shrinkwrap: a stamp-write failure leaves no stamp behind",
             stamp_path.exists(), False)
        # New content with no stamp must not read as current for the srcrev
        # the old (now-vanished) stamp named.
        case("write_shrinkwrap: is_current is False after a stamp-write "
             "failure, for the srcrev the old stamp named",
             app_lockfile.is_current(SRCREV, path=target), False)


# --- write_shrinkwrap creates a missing parent directory -------------------
#
# wisekiosk-frontend/ carries no other tracked file, so a fresh checkout has
# no such directory at all until write_shrinkwrap creates one.

def missing_parent_dir_cases():
    payload = b'{"lockfileVersion": 3, "packages": {}}'
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "wisekiosk-frontend" / "npm-shrinkwrap.json"
        rc = app_lockfile.write_shrinkwrap(payload, SRCREV, path=target)
        case("write_shrinkwrap: creates a missing parent directory", rc, 0)
        case("write_shrinkwrap: the shrinkwrap is written with the right "
             "content", target.read_bytes(), payload)
        case("write_shrinkwrap: the stamp is written with the right srcrev",
             app_lockfile.stamp_path_for(target).read_text(), SRCREV)


def main() -> int:
    src_inc_cases()
    raw_url_cases()
    fetch_lockfile_cases()
    stamp_path_for_cases()
    is_current_cases()
    write_shrinkwrap_cases()
    missing_parent_dir_cases()
    print(f"\npass={len(PASS)} fail={len(FAIL)} skip=0")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
