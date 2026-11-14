"""Specifies tests/verdicts/browser_restart.py: the restart decision over read_sample-shaped
samples, one test per outcome. No device, no DOM -- every sample is constructed.
"""

from verdicts.browser_restart import verdict

_OLD_NONCE = "1791490387376"
_NEW_NONCE = "1791490412009"


def _sample(nonce, state="applied", origin="http://localhost:8080"):
    """A read_sample-shaped sample with the given nonce, state and origin."""
    return {"nonce": nonce, "state": state, "cards": "0/0", "origin": origin}


def test_restarted_once_a_new_nonce_is_on_the_panel():
    outcome, _ = verdict(
        _sample(_OLD_NONCE),
        [_sample(_OLD_NONCE, state="loading"), _sample(_NEW_NONCE)],
    )
    assert outcome == "restarted"


def test_not_restarted_when_every_after_sample_carries_the_old_nonce():
    outcome, reason = verdict(_sample(_OLD_NONCE), [_sample(_OLD_NONCE), _sample(_OLD_NONCE)])
    assert outcome == "not-restarted"
    assert "nonce" in reason


def test_not_restarted_when_the_new_nonce_is_from_a_foreign_origin():
    outcome, reason = verdict(
        _sample(_OLD_NONCE), [_sample(_NEW_NONCE, origin="http://example.invalid")]
    )
    assert outcome == "not-restarted"
    assert "on-panel" in reason


def test_error_with_no_before_sample():
    outcome, reason = verdict(None, [_sample(_NEW_NONCE)])
    assert outcome == "error"
    assert "before the kill" in reason


def test_not_restarted_with_no_after_payload():
    outcome, reason = verdict(_sample(_OLD_NONCE), [None, None])
    assert outcome == "not-restarted"
    assert "after the kill" in reason
