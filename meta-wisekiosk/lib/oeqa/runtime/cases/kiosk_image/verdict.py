"""The image-content tier's own parse/judgement functions (#206, step 4 of #202, reduced to the
appliance's own needs -- the owner's lens, ~/.claude/plans/202/step4/brief.md "Subject and size"):
the effective ExecStart= a unit and its drop-ins resolve to, the bundle<->image hash tie, and path
presence (the display's own served files, and the binaries the verification tier's own checks
need). systemd-analyze verify's own outcome moved to cases/kiosk_units/verdict.py -- the appliance's
own systemd validating its own units runs on the board, not read as a host-side artefact.

Pure: strings, sets and dicts in, an (outcome, reason) tuple or a list out -- no self.target, no
subprocess, no network. case.py collects every input through the rootfs directory, the deployed
.ext4, or a host subprocess; this module only judges what came back.
"""
import configparser
import re

# -- effective ExecStart= (the image starts the kiosk display as designed) --
REQUIRED_DISPLAY_FLAGS = ("-s 0", "-dpms", "-nocursor")

_EXECSTART = re.compile(r"^ExecStart=(.*)$", re.MULTILINE)


def _service_section(text):
    """text's own [Service] section body (up to the next [Section] or end
    of text); empty string if text carries no [Service] section."""
    m = re.search(r"^\[Service\]\s*$(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


def _effective_execstart(unit_text, dropin_texts):
    """The merged ExecStart= command list systemd would run: unit_text's
    own [Service] ExecStart= lines, then each dropin_texts entry in the
    order given (the caller sorts drop-in filenames lexicographically
    before calling, systemd's own drop-in order), each bare 'ExecStart='
    resetting the accumulated list as systemd's own list-reset rule does,
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


def execstart_verdict(unit_text, dropin_texts, required=REQUIRED_DISPLAY_FLAGS):
    """Merges unit_text and dropin_texts (_effective_execstart, above),
    then "ok" if every required token is a substring of the merged
    command(s)' space-joined text; "error" naming exactly which are
    missing. An empty merge is its own "error" -- no ExecStart= survived
    at all, nothing to check."""
    effective = _effective_execstart(unit_text, dropin_texts)
    if not effective:
        return "error", "no ExecStart= remained after merging drop-ins -- nothing to check"
    joined = " ".join(effective)
    missing = [flag for flag in required if flag not in joined]
    if missing:
        return "error", f"missing {', '.join(missing)}"
    return "ok", "every required display flag is present"


# -- bundle <-> image hash tie (what was verified is what ships) ------------
def bundle_image_hash_verdict(manifest_text, ext4_sha256):
    """Parses manifest_text's own [image.rootfs] section's sha256= (RAUC's
    real manifest.raucm shape) and compares it to ext4_sha256 (hex,
    lowercase, already computed by the caller). "error" if the
    section/key is absent, or if the two disagree (naming both)."""
    parser = configparser.ConfigParser()
    try:
        parser.read_string(manifest_text)
    except configparser.Error:
        return "error", "the bundle manifest could not be parsed as INI"
    if not parser.has_option("image.rootfs", "sha256"):
        return "error", "the bundle manifest carries no [image.rootfs] sha256="
    bundle_sha256 = parser.get("image.rootfs", "sha256").strip()
    if bundle_sha256 != ext4_sha256:
        return "error", (
            f"the bundle names rootfs sha256={bundle_sha256}, the deployed "
            f".ext4 hashes to {ext4_sha256}")
    return "ok", f"the bundle and the deployed .ext4 agree on sha256={ext4_sha256}"


# -- path presence (the display's own served files; the binaries the --------
# -- verification tier's own checks need) ------------------------------------
REQUIRED_BINARIES = ("xprop", "xrandr", "xset", "import")


def path_presence_verdict(present, required):
    """"ok" iff every one of required's own members is in present; "error"
    naming exactly which are missing, in required's order. present may
    carry names/paths beyond what required asks for -- never trimmed.
    The one judgement shared by the display-files check and the
    required-binaries check, the only two path-presence questions this
    tier asks."""
    missing = [name for name in required if name not in present]
    if missing:
        return "error", f"missing: {', '.join(missing)}"
    return "ok", "every required path is present"
