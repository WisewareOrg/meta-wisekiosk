"""The device-side unit tier's own judgement: every unit the layer ships must be loaded, free of a
load error, and absent from systemd's own failed-unit list. Pure -- no self.target, no subprocess,
no network. case.py collects every input through `systemctl show`/`systemctl list-units --failed`;
this module only parses and judges what came back.
"""


def shipped_units_verdict(units, glob_description):
    """"error" when units is empty -- nothing was verified, never a pass;
    "ok" otherwise."""
    if not units:
        return "error", f"no shipped units found under {glob_description}"
    return "ok", f"{len(units)} shipped unit(s) found"


def show_properties(output):
    """`systemctl show -p ...`'s own `KEY=value` lines into a dict --
    property order is not guaranteed, so this never assumes a position."""
    properties = {}
    for line in output.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            properties[key] = value
    return properties


def failed_unit_names(output):
    """The set of unit names `systemctl list-units --failed --no-legend`
    reports -- every whitespace-separated token carrying a shipped unit's
    own suffix, independent of whether a leading status marker is present."""
    return {token for token in output.split()
            if token.endswith(".service") or token.endswith(".timer")}


def verdict(unit_properties, failed_units):
    """(outcome, reason) over every unit: unit_properties is {unit:
    {property: value}}, each from one `systemctl show` call;
    failed_units is failed_unit_names's own result, from one board-wide
    `systemctl list-units --failed` call. "error" naming every unit whose
    own LoadState is not "loaded", whose LoadError is non-empty, or which
    the failed-unit list names; "ok" once none do."""
    problems = []
    for unit, properties in unit_properties.items():
        load_state = properties.get("LoadState", "")
        load_error = properties.get("LoadError", "")
        if load_state != "loaded" or load_error:
            problems.append(f"{unit}: LoadState={load_state!r} LoadError={load_error!r}")
        if unit in failed_units:
            problems.append(f"{unit}: reported failed by systemctl list-units --failed")
    if problems:
        return "error", "; ".join(problems)
    return "ok", f"{len(unit_properties)} shipped unit(s) loaded, none failed"
