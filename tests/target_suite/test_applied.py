"""TST001: the applied-page check, judged by `verdicts.applied`."""

import time

from probe import APPLIED_WAIT_SECONDS
from verdicts.applied import read_sample, verdict

_POLL_SECONDS = 2


def test_page_applied(probe):
    """TST001: within 90 s of a restart, the page reaches state=applied.

    Args:
        probe: deploys `probe.js` and restarts the browser; yields a reader for the board's
            current window titles, raw.
    """
    deadline = time.monotonic() + APPLIED_WAIT_SECONDS
    samples = []
    while True:
        samples.append(read_sample(probe()))
        outcome, reason = verdict(samples)
        if outcome == "applied" or time.monotonic() >= deadline:
            break
        time.sleep(_POLL_SECONDS)

    if outcome == "error":
        raise RuntimeError(f"{outcome}:{reason}")
    assert outcome == "applied", f"{outcome}:{reason}"
