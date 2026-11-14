"""Whether the browser's own restart is real, judged from the sample read just before the kill
against the samples read after it (the nonce changes on a fresh page load, never on the same
instance). Pure: no device, no DOM.
"""

from verdicts.applied import on_panel


def verdict(before_sample, after_samples):
    """(outcome, reason) of the restart.

    Args:
        before_sample (dict): the on-panel `read_sample` result read just before the kill.
        after_samples (list[dict | None]): the `read_sample` results read after it.

    Returns:
        tuple[str, str]: "restarted" once an after sample is on the panel with a nonce different
            from `before_sample`'s; "not-restarted" if none is. The reason is empty for "restarted".
    """
    real = [sample for sample in after_samples if sample is not None]
    for sample in real:
        if on_panel(sample) and sample["nonce"] != before_sample["nonce"]:
            return "restarted", ""
    if not real:
        return "not-restarted", "no probe payload after the kill"
    return "not-restarted", "no on-panel sample carried a new nonce"
