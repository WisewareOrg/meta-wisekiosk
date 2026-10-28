"""Parse systemd unit files and resolve them the way systemd 255.22 reads them.

Three checks make up `check_image`: (1) the unit file is present; (2) every `ExecStart=`
resolves to a regular file; (3) every `WantedBy=`/`RequiredBy=` target has its `.wants/` or
`.requires/` entry, matched by name only -- the link's own target is a known limit, never
followed. stdlib only: this runs under the bench runner's interpreter, not bitbake's.
"""

import glob
import re
import subprocess
from pathlib import Path

# systemd's own bare-name search path.
DEFAULT_PATH = ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin")

# Priority order for a unit file and for a `.wants`/`.requires` link: first hit wins.
UNIT_DIRS = ("/etc/systemd/system", "/usr/local/lib/systemd/system", "/usr/lib/systemd/system")

# ExecStart= prefix characters (systemd "specifiers for command lines"); checked one at a
# time, so "!!" strips as two "!"s.
_EXEC_PREFIX_CHARS = "@-:+!"

# Linux's own symlink-loop bound (SYMLOOP_MAX); exceeding it is ELOOP whether or not the
# chain actually cycles.
_MAX_SYMLINK_HOPS = 40


class UnitError(Exception):
    """An `ExecStart=` cannot be resolved as systemd would resolve it."""


def parse(text):
    """Parse a unit file's ini-like sections.

    Args:
        text (str): the unit file's contents.

    Returns:
        dict[str, dict[str, list[str]]]: section name -> key -> values, in file order. A
        line ending in `\\` is joined with the next; `#`/`;` comments and blank lines are
        dropped; an empty assignment (`Key=`) resets that key's list.
    """
    joined_lines = []
    pending = ""
    for raw in text.splitlines():
        line = pending + raw
        if line.endswith("\\"):
            pending = line[:-1]
            continue
        pending = ""
        joined_lines.append(line)
    if pending:
        joined_lines.append(pending)

    sections = {}
    current = None
    for line in joined_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            sections.setdefault(current, {})
            continue
        if current is None or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        section = sections.setdefault(current, {})
        if value == "":
            section[key] = []
        else:
            section.setdefault(key, []).append(value)
    return sections


def _unescape_percent(token):
    """Collapse `%%` to a literal `%`; any other `%` is a specifier this checker cannot resolve.

    Args:
        token (str): an `ExecStart=` argv0, prefixes already stripped.

    Returns:
        str: `token` with every `%%` collapsed to `%`.

    Raises:
        UnitError: a `%` not followed by another `%`.
    """
    out = []
    i = 0
    while i < len(token):
        ch = token[i]
        if ch == "%":
            if i + 1 < len(token) and token[i + 1] == "%":
                out.append("%")
                i += 2
                continue
            raise UnitError(f"% specifier in {token!r}")
        out.append(ch)
        i += 1
    return "".join(out)


def _argv0_of(command_line):
    """Extract the first token of one `ExecStart=` command, prefixes already stripped.

    Args:
        command_line (str): the command text with its `@-:+!` prefixes removed.

    Returns:
        str: the quoted or bare first token.
    """
    if command_line.startswith('"'):
        end = command_line.find('"', 1)
        return command_line[1:end] if end != -1 else command_line[1:]
    return command_line.split(None, 1)[0] if command_line.split(None, 1) else command_line


def exec_argv0s(text):
    """List the argv0 of every `ExecStart=` line.

    Args:
        text (str): the unit file's contents.

    Returns:
        list[str]: one argv0 per `ExecStart=` line, in file order.

    Raises:
        UnitError: `ExecSearchPath=` is present, an argv0 is a lone `;`, or an argv0 carries
            a `%` specifier other than `%%`.
    """
    service = parse(text).get("Service", {})
    if "ExecSearchPath" in service:
        raise UnitError("ExecSearchPath= is not supported")
    argv0s = []
    for command_line in service.get("ExecStart", []):
        remainder = command_line
        while remainder and remainder[0] in _EXEC_PREFIX_CHARS:
            remainder = remainder[1:]
        token = _argv0_of(remainder)
        if token == ";":
            raise UnitError("a lone ';' separator has no command")
        argv0s.append(_unescape_percent(token))
    return argv0s


def install_targets(text):
    """Read a unit's `[Install]` targets.

    Args:
        text (str): the unit file's contents.

    Returns:
        tuple[list[str], list[str]]: (`WantedBy=` targets, `RequiredBy=` targets).
    """
    install = parse(text).get("Install", {})
    return (list(install.get("WantedBy", [])), list(install.get("RequiredBy", [])))


def _normalize_join(directory, target):
    """Join a symlink `target` onto the directory holding the link, lexically.

    Args:
        directory (str): the symlink's own directory (its resolved path).
        target (str): the symlink's target text, absolute or relative.

    Returns:
        str: the resulting absolute path, with every `.`/`..` resolved lexically.
    """
    base = target if target.startswith("/") else directory.rstrip("/") + "/" + target
    parts = []
    for part in base.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def _resolve_symlink_chain(path, lookup):
    """Follow `path` through symlinks to its final type.

    Args:
        path (str): an absolute path, already joined.
        lookup (Callable[[str], tuple[str, str | None] | None]): resolves one path.

    Returns:
        tuple[str | None, str]: (kind, resolved_path); kind is `None` if `path` (or a link
        in its chain) does not exist.

    Raises:
        UnitError: more than `_MAX_SYMLINK_HOPS` links are followed.
    """
    current = path
    for _hop in range(_MAX_SYMLINK_HOPS):
        entry = lookup(current)
        if entry is None:
            return None, current
        kind, target = entry
        if kind != "symlink":
            return kind, current
        parent = current.rsplit("/", 1)[0] or "/"
        current = _normalize_join(parent, target)
    raise UnitError(f"too many levels of symbolic links resolving {path!r}")


def resolve(argv0, lookup):
    """Resolve an `ExecStart=` argv0 the way systemd 255.22 resolves it.

    Args:
        argv0 (str): the command's first token -- a bare name or an absolute path.
        lookup (Callable[[str], tuple[str, str | None] | None]): resolves one path.
            Returns `("file"|"dir", None)`, `("symlink", target)`, or `None` if missing.

    Returns:
        str | None: the resolved regular file's absolute path, or `None` if it does not
        resolve to one.

    Raises:
        UnitError: `argv0` is a relative path with a `/` in it, or a symlink in its chain
            loops.
    """
    if not argv0.startswith("/"):
        if "/" in argv0:
            raise UnitError(f"relative path with a directory component: {argv0!r}")
        for directory in DEFAULT_PATH:
            found = resolve(f"{directory}/{argv0}", lookup)
            if found is not None:
                return found
        return None

    components = [part for part in argv0.split("/") if part]
    if not components:
        return None

    current = "/"
    for component in components[:-1]:
        kind, current = _resolve_symlink_chain(f"{current.rstrip('/')}/{component}", lookup)
        if kind != "dir":
            return None

    kind, resolved = _resolve_symlink_chain(f"{current.rstrip('/')}/{components[-1]}", lookup)
    return resolved if kind == "file" else None


def parse_stat(stdout, stderr):
    """Turn `debugfs -R "stat <path>"` output into a lookup result.

    Args:
        stdout (str): debugfs's stdout.
        stderr (str): debugfs's stderr.

    Returns:
        tuple[str, str | None] | None: `("file"|"dir", None)`, `("symlink", target)` for a
        fast link, `("symlink", None)` for a slow one (its target is read with `cat`), or
        `None` if `path` does not exist.
    """
    if "File not found by ext2_lookup" in stderr or not stdout.strip():
        return None
    type_match = re.search(r"Type:\s*(\S+)", stdout)
    if type_match is None:
        return None
    kind_word = type_match.group(1)
    if kind_word == "regular":
        return ("file", None)
    if kind_word == "directory":
        return ("dir", None)
    if kind_word == "symlink":
        target_match = re.search(r'Fast link dest:\s*"([^"]*)"', stdout)
        return ("symlink", target_match.group(1) if target_match else None)
    return None


def _debugfs(image, command):
    """Run one read-only debugfs command against `image`.

    Args:
        image (str): the rootfs image path.
        command (str): the debugfs command, e.g. `stat /path`.

    Returns:
        subprocess.CompletedProcess: with `stdout`/`stderr` captured as text.
    """
    return subprocess.run(
        ["debugfs", "-R", command, image], capture_output=True, text=True, check=False
    )


def debugfs_lookup(image):
    """Build a `lookup` callable backed by `debugfs -R "stat ..."` against `image`.

    A slow symlink (no `Fast link dest:` in `stat`) is completed with `cat`.

    Args:
        image (str): the rootfs image path.

    Returns:
        Callable[[str], tuple[str, str | None] | None]: `lookup(path)`.
    """

    def lookup(path):
        result = _debugfs(image, f"stat {path}")
        entry = parse_stat(result.stdout, result.stderr)
        if entry is None:
            return None
        kind, target = entry
        if kind == "symlink" and target is None:
            target = _debugfs(image, f"cat {path}").stdout
        return (kind, target)

    return lookup


def debugfs_read(image):
    """Build a `read` callable backed by `debugfs -R "cat ..."` against `image`.

    Args:
        image (str): the rootfs image path.

    Returns:
        Callable[[str], str | None]: `read(path)`, `None` if `path` does not exist.
    """

    def read(path):
        result = _debugfs(image, f"cat {path}")
        if "File not found by ext2_lookup" in result.stderr:
            return None
        return result.stdout

    return read


def _has_enable_link(unit_name, target_name, suffix, lookup):
    """Check every unit dir for `target_name.<suffix>/unit_name`, by name only.

    Args:
        unit_name (str): the unit file's basename.
        target_name (str): the `WantedBy=`/`RequiredBy=` target.
        suffix (str): `"wants"` or `"requires"`.
        lookup (Callable[[str], tuple[str, str | None] | None]): resolves one path.

    Returns:
        bool: whether the entry exists, under any unit dir. Its own link target is never
            followed -- a dangling one still counts.
    """
    return any(
        lookup(f"{unit_dir}/{target_name}.{suffix}/{unit_name}") is not None
        for unit_dir in UNIT_DIRS
    )


def _check_one_unit(name, lookup, read):
    """Check (1)/(2)/(3) for one unit.

    Args:
        name (str): the unit file's basename.
        lookup (Callable[[str], tuple[str, str | None] | None]): resolves one path.
        read (Callable[[str], str | None]): reads one file's text.

    Returns:
        str | None: a `"<unit>: (<n>) <reason>"` failure, or `None` if `name` passes.

    Raises:
        UnitError: an `ExecStart=` cannot be resolved; the caller converts this to a (2)
            failure string.
    """
    unit_path = None
    for unit_dir in UNIT_DIRS:
        candidate = f"{unit_dir}/{name}"
        entry = lookup(candidate)
        if entry is None:
            continue
        kind, target = entry
        if kind == "symlink":
            if target == "/dev/null":
                return f"{name}: (1) masked"
            resolved_kind, resolved_path = _resolve_symlink_chain(candidate, lookup)
            if resolved_kind is None:
                continue
            unit_path = resolved_path
        else:
            unit_path = candidate
        break
    if unit_path is None:
        return f"{name}: (1) unit file not found"

    text = read(unit_path)
    if text is None:
        return f"{name}: (1) unit file not found"

    if not name.endswith(".timer"):
        for argv0 in exec_argv0s(text):
            if resolve(argv0, lookup) is None:
                return f"{name}: (2) ExecStart does not resolve: {argv0!r}"

    wanted_by, required_by = install_targets(text)
    missing = [t for t in wanted_by if not _has_enable_link(name, t, "wants", lookup)]
    missing += [t for t in required_by if not _has_enable_link(name, t, "requires", lookup)]
    if missing:
        return f"{name}: (3) not enabled for {', '.join(missing)}"
    return None


def check_image(unit_names, lookup, read):
    """Check every named unit: (1) present, (2) `ExecStart=` resolves, (3) enabled by name.

    Args:
        unit_names (list[str]): unit file basenames to check.
        lookup (Callable[[str], tuple[str, str | None] | None]): resolves one path.
        read (Callable[[str], str | None]): reads one file's text.

    Returns:
        list[str]: one `"<unit>: (<n>) <reason>"` string per failing unit. Never raises
        `UnitError` -- an unresolvable `ExecStart=` becomes that unit's own (2) failure.
    """
    failures = []
    for name in unit_names:
        try:
            failure = _check_one_unit(name, lookup, read)
        except UnitError as exc:
            failure = f"{name}: (2) {exc}"
        if failure is not None:
            failures.append(failure)
    return failures


def shipped_units():
    """List every unit/timer file this layer's recipes ship, by basename.

    Returns:
        list[str]: basenames globbed from `meta-wisekiosk/recipes-*/**/*.service` and
        `*.timer`, resolved against this repo's root.
    """
    root = Path(__file__).resolve().parent.parent.parent
    names = []
    for pattern in ("*.service", "*.timer"):
        names += [
            Path(match).name
            for match in glob.glob(str(root / "meta-wisekiosk" / "recipes-*" / "**" / pattern), recursive=True)
        ]
    return names
