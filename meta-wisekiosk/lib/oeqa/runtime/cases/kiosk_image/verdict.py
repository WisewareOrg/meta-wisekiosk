"""The image-content tier's own parse/judgement functions: the effective ExecStart= a unit and its
drop-ins resolve to, and path presence.

Pure: strings, sets and dicts in, an (outcome, reason) tuple out -- no self.target, no subprocess,
no network. case.py collects every input; this module only judges what came back.
"""
import re

# -- effective ExecStart= --
REQUIRED_DISPLAY_FLAGS = ("-s 0", "-dpms", "-nocursor")

_EXECSTART = re.compile(r"^ExecStart[ \t]*=[ \t]*(.*)$", re.MULTILINE)


def _service_section(text):
    """text's own [Service] section body; empty string if text carries no
    [Service] section."""
    m = re.search(r"^\[Service\]\s*$(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


def _effective_execstart(unit_text, dropin_texts):
    """The merged ExecStart= command list systemd would run: unit_text's
    own [Service] ExecStart= lines, then each dropin_texts entry in the
    order given, each bare 'ExecStart=' resetting the accumulated list,
    any other 'ExecStart=<cmd>' appending <cmd> stripped. A line outside
    [Service] is ignored."""
    commands = []
    for text in (unit_text, *dropin_texts):
        for value in _EXECSTART.findall(_service_section(text)):
            value = value.strip()
            if value == "":
                commands = []
            else:
                commands.append(value)
    return commands


def _contains_token_sequence(tokens, wanted):
    n = len(wanted)
    return any(tokens[i:i + n] == wanted for i in range(len(tokens) - n + 1))


def execstart_verdict(unit_text, dropin_texts):
    """Merges unit_text and dropin_texts (_effective_execstart, above),
    then "ok" if every REQUIRED_DISPLAY_FLAGS token sequence appears in
    the merged command(s)' own token list; "error" naming exactly which
    are missing. An empty merge is its own "error"."""
    effective = _effective_execstart(unit_text, dropin_texts)
    if not effective:
        return "error", "no ExecStart= remained after merging drop-ins -- nothing to check"
    tokens = " ".join(effective).split()
    missing = [flag for flag in REQUIRED_DISPLAY_FLAGS
               if not _contains_token_sequence(tokens, flag.split())]
    if missing:
        return "error", f"missing {', '.join(missing)}"
    return "ok", "every required display flag is present"


# -- path presence --
REQUIRED_BINARIES = ("xprop", "xrandr", "xset", "import")


def path_presence_verdict(present, required):
    """"ok" iff every one of required's own members is in present;
    "error" naming exactly which are missing, in required's order."""
    missing = [name for name in required if name not in present]
    if missing:
        return "error", f"missing: {', '.join(missing)}"
    return "ok", "every required path is present"
