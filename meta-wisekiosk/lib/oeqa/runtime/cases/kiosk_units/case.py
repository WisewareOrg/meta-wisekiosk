from pathlib import Path

from framework.base import WiseKioskCase

from . import verdict

# The repo root, resolved the same way framework/base.py resolves it for its own git calls.
_REPO_ROOT = Path(__file__).resolve().parents[6]


UNIT_GLOBS = ("meta-wisekiosk/recipes-*/**/*.service", "meta-wisekiosk/recipes-*/**/*.timer")

SHOW_PROPERTIES = "LoadState,LoadError,ActiveState,Result"


def _shipped_units():
    """Every *.service/*.timer file meta-wisekiosk's own recipes install,
    derived from the layer rather than hand-kept."""
    paths = [p for pattern in UNIT_GLOBS for p in _REPO_ROOT.glob(pattern)]
    return tuple(sorted(p.name for p in paths))


SHIPPED_UNITS = _shipped_units()


class KioskUnitsTest(WiseKioskCase):
    """The appliance's own systemd reporting on its own shipped units: one
    `systemctl show` call per unit in SHIPPED_UNITS, plus one board-wide
    `systemctl list-units --failed` call, on the board over SSH."""

    def test_units_loaded(self):
        outcome, reason = verdict.shipped_units_verdict(SHIPPED_UNITS, ", ".join(UNIT_GLOBS))
        if outcome != "ok":
            self.fail(reason)

        unit_properties = {}
        for unit in SHIPPED_UNITS:
            _status, output = self.target.run(f"systemctl show -p {SHOW_PROPERTIES} {unit}")
            unit_properties[unit] = verdict.show_properties(output)

        _status, failed_output = self.target.run("systemctl list-units --failed --no-legend")
        failed_units = verdict.failed_unit_names(failed_output)

        outcome, reason = verdict.verdict(unit_properties, failed_units)
        if outcome != "ok":
            self.fail(reason)
