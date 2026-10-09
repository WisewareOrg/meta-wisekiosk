"""The device-side unit-wellformedness tier's own judgement: `systemd-analyze verify`'s own
outcome, and the extraction of every unit name it reports missing. `data.mount` is produced at
boot by systemd's fstab generator, never a unit file in the image; `verify` never sees it, and a
"Unit X not found" line is excused -- not a defect -- exactly when the board's own
`systemctl is-active X` says X is running.

Pure: a returncode, verify's own text, and a {name: is-active answer} map in, an (outcome, reason)
tuple or a name set out -- no self.target, no subprocess, no network. case.py collects every input;
this module only judges what came back.
"""
import re

NOT_FOUND = re.compile(r"Unit (\S+) not found")


def not_found_names(output):
    """The set of unit names output's own "Unit X not found" lines report missing."""
    return set(NOT_FOUND.findall(output))


def verdict(status, output, active_units):
    """status: systemd-analyze verify's own exit code. output: its
    combined stdout/stderr. active_units: {name: systemctl is-active's
    own answer} for every name not_found_names(output) reports. A
    "Unit X not found" line is dropped (excused) when active_units maps
    that name to "active"; every other line survives. "error" naming
    whatever survives, if anything; else "error" naming the bare status
    when status is non-zero and nothing was excused either (a silent
    failure with no diagnostic to excuse); else "ok"."""
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
