"""The device-side unit-wellformedness tier's own judgement. `data.mount` is produced at boot by
systemd's fstab generator, never a unit file in the image; `verify` never sees it, and a "Unit X
not found" line is excused -- not a defect -- exactly when the board's own `systemctl is-active X`
says X is running.

Pure -- no self.target, no subprocess, no network. case.py collects every input.
"""
import re

NOT_FOUND = re.compile(r"Unit (\S+) not found")


def not_found_names(output):
    """The set of unit names output's own "Unit X not found" lines report missing."""
    return set(NOT_FOUND.findall(output))


def shipped_units_verdict(units):
    """"error" when units is empty -- nothing was verified, never a pass;
    "ok" otherwise."""
    if not units:
        return "error", "no shipped units found under meta-wisekiosk/recipes-*/**/*.service, *.timer"
    return "ok", f"{len(units)} shipped unit(s) found"


def verdict(status, output, active_units):
    """"ok" iff status == 0 and every line is absent or excused; "error"
    naming what survives, or the bare status if nothing does."""
    remaining = []
    excused_any = False
    for line in output.splitlines():
        if not line.strip():
            continue
        match = NOT_FOUND.search(line)
        if match and active_units.get(match.group(1)) == "active":
            excused_any = True
            continue
        remaining.append(line)
    if remaining:
        return "error", "; ".join(remaining)
    if status != 0 and not excused_any:
        return "error", f"systemd-analyze verify exited {status} with no diagnostic"
    return "ok", "systemd-analyze verify reported no problems once generator-provided mounts are accounted for"
