#!/usr/bin/env python3
"""Self-test for doc-image.py's ssh_commands(). Run by hand -- not wired into
just guards or ci-guards.sh.

    doc-image-test.py    -- every case, both directions

ssh_commands() splits a captured `ssh root@... '<script>'` body on
`[;&|]+` to find each command's leading word. That character class also
matches the shell's REDIRECTION operators (`2>&1`, `>&2`, `&>`), which are
not command separators -- the digit or path fragment left over from a
split redirection reads as a phantom command, and doc-image.py reports it
"not in image" on every build, failing `just verify` for a line that never
invoked anything.
"""
import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

PASS, FAIL = [], []


def case(name, got, want):
    (PASS if got == want else FAIL).append(name)
    if got != want:
        print(f"FAIL  {name}\n        want {want!r}\n        got  {got!r}")


def load(name):
    """doc-image.py, imported by path: the filename is not a module name."""
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


doc_image = load("doc-image")


def run(script):
    """The names ssh_commands() yields for a script captured as
    `ssh root@host '<script>'` -- the exact shape SSH_INVOCATION matches."""
    text = f"ssh root@host '{script}'"
    return [name for name, _line in doc_image.ssh_commands(text)]


def ssh_commands_cases():
    case("semicolon + pipe, one redirection",
         run("grep a /f; rauc status 2>&1 | grep b"),
         ["grep", "rauc", "grep"])
    case("stderr-to-stdout before a command name",
         run("cmd >&2"),
         ["cmd"])
    case("combined stdout+stderr redirect",
         run("cmd &>/dev/null"),
         ["cmd"])
    case("logical and",
         run("a && b"),
         ["a", "b"])
    case("background/job control",
         run("a & b"),
         ["a", "b"])
    case("logical or",
         run("a || b"),
         ["a", "b"])
    case("redirection, then a real separator, then a real command",
         run("cmd 2>&1 >/dev/null; next"),
         ["cmd", "next"])


def main() -> int:
    ssh_commands_cases()
    print(f"\npass={len(PASS)} fail={len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
