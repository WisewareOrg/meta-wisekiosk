#!/usr/bin/env python3
"""Self-test for tools/app-lockfile.py. Run by `just guards` and by CI.

    app-lockfile-test.py        -- every case

`app-lockfile.py` writes the app's npm shrinkwrap by fetching its own
frontend/package-lock.json straight from the pinned commit, never running npm.
Three importable seams: `_src_inc_fields(src_inc)` parses the pin and clone
URL from a wisekiosk-src.inc path handed to it (a fixture here, the real file
in production); `fetch_lockfile(url, srcrev)` is the only network-touching
call, stubbed here by replacing `urllib.request.urlopen` for the call's
duration -- never a real fetch; `write_shrinkwrap(content, path)` validates
and writes to a path handed to it (a fixture here, SHRINKWRAP_PATH inside the
real repo tree in production). No case here ever touches the real
wisekiosk-src.inc or writes into the real repo tree.
"""
import contextlib
import importlib.util
import io
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


# --- write_shrinkwrap: validate, then write verbatim to a fixture path -----

def write_shrinkwrap_cases():
    payload = b'{"lockfileVersion": 3, "packages": {}}'

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "npm-shrinkwrap.json"
        rc = app_lockfile.write_shrinkwrap(payload, path=target)
        case("write_shrinkwrap: valid JSON returns 0", rc, 0)
        case("write_shrinkwrap: bytes are written verbatim",
             target.read_bytes(), payload)

    # THE case: invalid JSON refuses and leaves no file at all, rather than a
    # zero-byte or partial one an operator's build would then npm-install
    # against silently.
    with tempfile.TemporaryDirectory() as tmp, \
         contextlib.redirect_stderr(io.StringIO()):
        target = Path(tmp) / "npm-shrinkwrap.json"
        rc = app_lockfile.write_shrinkwrap(b"not json at all", path=target)
        case("write_shrinkwrap: invalid JSON refuses (non-zero)", rc != 0, True)
        case("write_shrinkwrap: invalid JSON leaves no file behind",
             target.exists(), False)

    # Must-not-fire: a refusal happens before write_shrinkwrap ever calls
    # `path.write_bytes` (JSON validation runs first), so an existing file at
    # the target is left alone. This does NOT prove the write itself is
    # atomic/partial-write-safe -- write_shrinkwrap's current write is a
    # single non-atomic `path.write_bytes`, and this case cannot fail on a
    # write that starts and is interrupted. See the tmp+os.replace follow-up
    # content-reviewer requested from the implementer.
    with tempfile.TemporaryDirectory() as tmp, \
         contextlib.redirect_stderr(io.StringIO()):
        target = Path(tmp) / "npm-shrinkwrap.json"
        target.write_bytes(payload)
        app_lockfile.write_shrinkwrap(b"not json at all", path=target)
        case("write_shrinkwrap: a refusal leaves an existing file untouched",
             target.read_bytes(), payload)


def main() -> int:
    src_inc_cases()
    raw_url_cases()
    fetch_lockfile_cases()
    write_shrinkwrap_cases()
    print(f"\npass={len(PASS)} fail={len(FAIL)} skip=0")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
