"""TST010: on the booted board, every unit meta-wisekiosk's own recipes ship is loaded with no
load error, and none of them appears in systemd's own failed-unit list.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

UNIT_GLOBS = ("meta-wisekiosk/recipes-*/**/*.service", "meta-wisekiosk/recipes-*/**/*.timer")
SHOW_PROPERTIES = "LoadState,LoadError"


def _shipped_units():
    """Every *.service/*.timer file meta-wisekiosk's own recipes install, derived from the
    layer rather than hand-kept."""
    paths = [p for pattern in UNIT_GLOBS for p in _REPO_ROOT.glob(pattern)]
    return tuple(sorted(p.name for p in paths))


SHIPPED_UNITS = _shipped_units()


def _show_properties(lines):
    """`systemctl show -p ...`'s own `KEY=value` lines into a dict -- property order is not
    guaranteed, so this never assumes a position."""
    properties = {}
    for line in lines:
        if "=" in line:
            key, _, value = line.partition("=")
            properties[key] = value
    return properties


def _failed_unit_names(lines):
    """Every unit name `systemctl list-units --failed --no-legend` reports -- the first token
    carrying a dot on each line, skipping an optional leading status marker, regardless of unit
    type or whether it is a unit this layer ships."""
    names = []
    for line in lines:
        for token in line.split():
            if "." in token:
                names.append(token)
                break
    return names


def test_units_loaded(target):
    driver = target.get_driver("SSHDriver")
    assert SHIPPED_UNITS, "no shipped units found"

    problems = []
    for unit in SHIPPED_UNITS:
        stdout, _, _ = driver.run(f"systemctl show -p {SHOW_PROPERTIES} {unit}")
        properties = _show_properties(stdout)
        load_state = properties.get("LoadState", "")
        load_error = properties.get("LoadError", "")
        if load_state != "loaded" or load_error:
            problems.append(f"{unit}: LoadState={load_state!r} LoadError={load_error!r}")

    stdout, _, _ = driver.run("systemctl list-units --failed --no-legend")
    for unit in _failed_unit_names(stdout):
        problems.append(f"{unit}: reported failed by systemctl list-units --failed")

    assert not problems, "; ".join(problems)
