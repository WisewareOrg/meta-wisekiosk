"""Whether the browser's own restart is real, judged from the sample read just before the kill
against the samples read after it (kiosk_applied's own probe payload -- the nonce changes on a
fresh page load, never on the same instance). Pure: no device, no DOM.
"""


def verdict(before_sample, after_samples):
    """(outcome, reason): "restarted" once an after sample reads state=applied with a nonce
    different from before_sample's own; "not-restarted" if the deadline passed with every after
    sample either missing, non-applied, or carrying the old nonce; "error" only when there was no
    baseline to compare against."""
    if before_sample is None:
        return "error", "no probe payload before the kill"
    real = [sample for sample in after_samples if sample is not None]
    for sample in real:
        if sample["state"] == "applied" and sample["nonce"] != before_sample["nonce"]:
            return "restarted", ""
    if not real:
        return "not-restarted", "no probe payload after the kill"
    return "not-restarted", "no applied sample carried a new nonce"
