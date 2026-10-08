"""Specifies cases/kiosk_browser_restart/verdict.py: the restart decision against kiosk_applied's
own sample shape (nonce/state/cards/faulted/unreachable), one test per outcome.

No device, no DOM -- every sample is constructed, shaped like a real read_sample() result.
"""

from oeqa.runtime.cases.kiosk_browser_restart.verdict import verdict


def _sample(nonce, state="applied"):
    return {"nonce": nonce, "state": state, "cards": "-/-", "faulted": 0, "unreachable": 0}


def test_verdict_restarted_once_a_new_nonce_reads_applied():
    outcome, reason = verdict(
        before_sample=_sample("1762000000.1"),
        after_samples=[_sample("1762000000.1", state="loading"), _sample("1762000041.7")],
    )
    assert outcome == "restarted"


def test_verdict_not_restarted_when_every_after_sample_carries_the_old_nonce():
    outcome, reason = verdict(
        before_sample=_sample("1762000000.1"),
        after_samples=[_sample("1762000000.1"), _sample("1762000000.1")],
    )
    assert outcome == "not-restarted"
    assert "nonce" in reason.lower()


def test_verdict_not_restarted_when_no_after_sample_ever_reads_applied():
    outcome, reason = verdict(
        before_sample=_sample("1762000000.1"),
        after_samples=[_sample("1762000000.1", state="loading"), None],
    )
    assert outcome == "not-restarted"


def test_verdict_error_with_no_before_sample():
    outcome, reason = verdict(before_sample=None, after_samples=[_sample("1762000041.7")])
    assert outcome == "error"
    assert "before the kill" in reason


def test_verdict_error_with_no_after_sample_at_all():
    outcome, reason = verdict(before_sample=_sample("1762000000.1"), after_samples=[None, None])
    assert outcome == "error"
    assert "after the kill" in reason
