"""TST010: on the booted board, every unit meta-wisekiosk's own recipes ship is loaded with no
load error, and systemd's own failed-unit list is empty.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

UNIT_GLOBS = ("meta-wisekiosk/recipes-*/**/*.service", "meta-wisekiosk/recipes-*/**/*.timer")


def _shipped_units():
    """Name every unit file meta-wisekiosk's own recipes install.

    Derived from the layer's own recipe tree by glob, rather than hand-kept, so a unit a recipe
    adds or drops is picked up without editing this test.

    Returns:
        tuple[str, ...]: Every shipped `*.service`/`*.timer` file's name, sorted.
    """
    paths = [p for pattern in UNIT_GLOBS for p in _REPO_ROOT.glob(pattern)]
    return tuple(sorted(p.name for p in paths))


SHIPPED_UNITS = _shipped_units()


def test_units_loaded(target):
    """TST010: every shipped unit is loaded with no load error; nothing on the board has failed.

    Each check asks systemd for exactly one bare value (`--value`, no key to strip), so there is
    no text to parse here: `systemctl show -p LoadState --value <unit>` must print `loaded` and
    `systemctl show -p LoadError --value <unit>` must print nothing, for every unit in
    `SHIPPED_UNITS`; `systemctl list-units --failed --plain --no-legend` must exit zero with no
    output at all. Every call's own exit status is asserted first, so an ssh or systemctl failure
    never reads as a clean answer.

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.
    """
    driver = target.get_driver("SSHDriver")
    assert SHIPPED_UNITS, "no shipped units found"

    for unit in SHIPPED_UNITS:
        stdout, stderr, rc = driver.run(f"systemctl show -p LoadState --value {unit}")
        assert rc == 0, f"{unit}: systemctl show -p LoadState exited {rc}: {stderr}"
        assert "".join(stdout).strip() == "loaded", f"{unit}: LoadState={stdout!r}"

        stdout, stderr, rc = driver.run(f"systemctl show -p LoadError --value {unit}")
        assert rc == 0, f"{unit}: systemctl show -p LoadError exited {rc}: {stderr}"
        assert not "".join(stdout).strip(), f"{unit}: LoadError={stdout!r}"

    stdout, stderr, rc = driver.run("systemctl list-units --failed --plain --no-legend")
    assert rc == 0, f"systemctl list-units --failed exited {rc}: {stderr}"
    assert not any(line.strip() for line in stdout), f"failed units reported: {stdout}"
