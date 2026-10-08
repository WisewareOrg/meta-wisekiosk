"""The device-side unit-wellformedness tier's own judgement (#206, step 4 of #202, the owner's
lens correction: `systemd-analyze verify` is the appliance's own systemd validating its own units,
so it runs on the board over SSH, never as a host-side artefact read).

Pure: a returncode and text in, an (outcome, reason) tuple out -- no self.target, no subprocess,
no network. case.py collects every input through self.target.run; this module only judges what
came back.
"""


def systemd_analyze_verdict(returncode, stderr_text):
    """Grounded on this host's real systemd 259 `systemd-analyze verify`: a
    load/start failure is a nonzero returncode ("error", naming every
    non-blank stderr line); a residual non-fatal note with returncode 0 is
    "warning" (not "ok", and not distinguishable from "ok" by returncode
    alone); returncode 0 with no residual text is "ok". case.py is
    responsible for handing this function text already scoped to the unit
    under test: a real verify call also emits unrelated notices about
    OTHER shipped units loaded while resolving the one named."""
    if returncode == 0:
        if stderr_text.strip():
            return "warning", stderr_text.strip()
        return "ok", "systemd-analyze verify reported no problems"
    lines = [line for line in stderr_text.splitlines() if line.strip()]
    if lines:
        return "error", "; ".join(lines)
    return "error", f"systemd-analyze verify exited {returncode} with no output"
