import re

from framework.base import WiseKioskCase

from . import verdict

# meta-wisekiosk's own shipped .service/.timer files (grepped from
# recipes-core and recipes-wisekiosk) -- never the whole image's ~190
# shipped units, most of which belong to poky/meta-openembedded layers
# this ticket does not own.
SHIPPED_UNITS = (
    "kiosk.service",
    "wisekiosk.service",
    "kiosk-soak.service",
    "kiosk-soak.timer",
    "kiosk-netcheck.service",
    "kiosk-journal-flush.service",
    "kiosk-timesync-dir.service",
    "kiosk-bootprofile.service",
    "kiosk-provision.service",
    "kiosk-cpufreq-cap.service",
)


def _own_unit_lines(output_text, unit_name):
    """output_text's own lines that name unit_name, joined back into text.
    A real verify call also reports on every OTHER unit it loads while
    resolving the one named; without this filter that cross-talk alone
    can keep a unit's own output non-empty with nothing the unit itself
    caused. Bounded with a word boundary so "kiosk.service" never matches
    inside "wisekiosk.service" -- a real collision in SHIPPED_UNITS."""
    pattern = re.compile(r"(?<![\w.-])" + re.escape(unit_name) + r"(?![\w.-])")
    return "\n".join(line for line in output_text.splitlines() if pattern.search(line))


class KioskUnitsTest(WiseKioskCase):
    """The appliance's own systemd validating its own shipped units
    (#206): one `systemd-analyze verify` call per unit in SHIPPED_UNITS,
    on the board over SSH, each scoped to its own unit's output before
    verdict.systemd_analyze_verdict judges it -- never --root over the
    build's own rootfs, since the generators (fstab, among others) that
    the board's own boot already ran are what this check needs live.
    `--generators=yes` makes verify run those generators itself (data.mount
    among them), rather than treating a unit that Requires=/Wants= one as
    unverifiable; it needs the root privileges the SSH target already
    runs as."""

    def test_units_well_formed(self):
        problems = []
        for unit in SHIPPED_UNITS:
            status, output = self.target.run(f"systemd-analyze verify --generators=yes {unit}")
            scoped = _own_unit_lines(output, unit)
            outcome, reason = verdict.systemd_analyze_verdict(status, scoped)
            if outcome == "error":
                problems.append(f"{unit}: {reason}")
        if problems:
            self.fail("\n".join(problems))
