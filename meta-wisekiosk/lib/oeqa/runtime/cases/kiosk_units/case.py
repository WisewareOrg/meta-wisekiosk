from pathlib import Path

from framework.base import WiseKioskCase

from . import verdict

# The repo root, resolved the same way framework/base.py resolves it for its own git calls.
_REPO_ROOT = Path(__file__).resolve().parents[6]


def _shipped_units():
    """Every *.service/*.timer file meta-wisekiosk's own recipes install,
    derived from the layer rather than hand-kept."""
    paths = (*_REPO_ROOT.glob("meta-wisekiosk/recipes-*/**/*.service"),
             *_REPO_ROOT.glob("meta-wisekiosk/recipes-*/**/*.timer"))
    return tuple(sorted(p.name for p in paths))


SHIPPED_UNITS = _shipped_units()


class KioskUnitsTest(WiseKioskCase):
    """The appliance's own systemd validating its own shipped units: one
    `systemd-analyze verify` call per unit in SHIPPED_UNITS, on the board
    over SSH."""

    def test_units_well_formed(self):
        problems = []
        for unit in SHIPPED_UNITS:
            status, output = self.target.run(f"systemd-analyze verify {unit}")
            not_found = verdict.not_found_names(output)
            active_units = {
                name: self.target.run(f"systemctl is-active {name}")[1].strip()
                for name in not_found
            }
            outcome, reason = verdict.verdict(status, output, active_units)
            if outcome == "error":
                problems.append(f"{unit}: {reason}")
        if problems:
            self.fail("\n".join(problems))
