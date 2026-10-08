"""Specifies cases/kiosk_browser_restart/verdict.py: the restart decision against kiosk_applied's
own sample shape (nonce/state/cards/faulted/unreachable), one test per outcome.

No device, no DOM -- every sample is constructed, shaped like a real read_sample() result: the
probe's own nonce is performance.timeOrigin, an integer-millisecond string.
"""

from oeqa.runtime.cases.kiosk_browser_restart.verdict import verdict

_OLD_NONCE = "1791490387376"
_NEW_NONCE = "1791490412009"


def _sample(nonce, state="applied"):
    return {"nonce": nonce, "state": state, "cards": "-/-", "faulted": 0, "unreachable": 0}


def test_verdict_restarted_once_a_new_nonce_reads_applied():
    outcome, reason = verdict(
        before_sample=_sample(_OLD_NONCE),
        after_samples=[_sample(_OLD_NONCE, state="loading"), _sample(_NEW_NONCE)],
    )
    assert outcome == "restarted"


def test_verdict_not_restarted_when_every_after_sample_carries_the_old_nonce():
    outcome, reason = verdict(
        before_sample=_sample(_OLD_NONCE),
        after_samples=[_sample(_OLD_NONCE), _sample(_OLD_NONCE)],
    )
    assert outcome == "not-restarted"
    assert "nonce" in reason.lower()


def test_verdict_error_with_no_before_sample():
    outcome, reason = verdict(before_sample=None, after_samples=[_sample(_NEW_NONCE)])
    assert outcome == "error"
    assert "before the kill" in reason


def test_verdict_not_restarted_with_zero_after_samples():
    outcome, reason = verdict(before_sample=_sample(_OLD_NONCE), after_samples=[None, None])
    assert outcome == "not-restarted"
    assert "after the kill" in reason
