"""The device-side unit tier's own judgement: every unit the layer ships must be loaded and free
of a load error, and the board must report no failed unit of any kind. Pure -- no self.target, no
subprocess, no network. case.py collects every input through `systemctl show`/`systemctl
list-units --failed`; this module only parses and judges what came back.
"""


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
    """Every unit name `systemctl list-units --failed --no-legend` reports --
    the first column carrying a dot on each line, skipping an optional
    leading status marker, regardless of unit type or whether it is a unit
    this layer ships."""
    names = []
    for line in output.splitlines():
        for token in line.split():
            if "." in token:
                names.append(token)
                break
    return names


def verdict(unit_properties, failed_units):
    """(outcome, reason) over every shipped unit: unit_properties is {unit:
    {property: value}}, each from one `systemctl show` call; failed_units is
    failed_unit_names's own result, from one board-wide `systemctl
    list-units --failed` call naming every failed unit on the board, not
    only a shipped one. "error" when no shipped units were checked at all,
    or naming every shipped unit whose own LoadState is not "loaded" or
    whose LoadError is non-empty, and every unit the failed list names;
    "ok" once none of that holds."""
    if not unit_properties:
        return "error", "no shipped units found"
    problems = []
    for unit, properties in unit_properties.items():
        load_state = properties.get("LoadState", "")
        load_error = properties.get("LoadError", "")
        if load_state != "loaded" or load_error:
            problems.append(f"{unit}: LoadState={load_state!r} LoadError={load_error!r}")
    for unit in failed_units:
        problems.append(f"{unit}: reported failed by systemctl list-units --failed")
    if problems:
        return "error", "; ".join(problems)
    return "ok", f"{len(unit_properties)} shipped unit(s) loaded, none failed"
