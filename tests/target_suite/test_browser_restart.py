"""TST005: the browser-restart check, judged by `verdicts.browser_restart`."""

import time

from verdicts.applied import verdict as applied_verdict
from verdicts.browser_restart import verdict

_APPLIED_WAIT_SECONDS = 90
_DEADLINE_SECONDS = 60
_POLL_SECONDS = 2


def _wait_applied(probe, deadline_s):
    """Poll `probe` until a sample reads state=applied, or raise at the deadline.

    Args:
        probe: The `probe` fixture's own reader callable.
        deadline_s (float): Seconds to keep polling.

    Returns:
        dict: The first sample whose state is "applied".

    Raises:
        RuntimeError: `deadline_s` elapsed with no applied sample.
    """
    deadline = time.monotonic() + deadline_s
    samples = []
    while True:
        samples.append(probe())
        outcome, reason = applied_verdict(samples)
        if outcome == "applied":
            return samples[-1]
        if time.monotonic() >= deadline:
            raise RuntimeError(f"the page did not apply within {deadline_s}s ({outcome}:{reason})")
        time.sleep(_POLL_SECONDS)


def test_browser_restart(target, probe):
    """TST005: once the browser dies, it comes back on its own and re-applies the page.

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.
        probe: deploys `probe.js` and restarts the browser; yields a reader for its latest
            sample.
    """
    driver = target.get_driver("SSHDriver")
    before_sample = _wait_applied(probe, _APPLIED_WAIT_SECONDS)

    stdout, stderr, rc = driver.run("pgrep -x surf")
    if rc != 0 or not stdout:
        raise RuntimeError(f"surf is not running before the kill: {stderr}")
    _stdout, stderr, rc = driver.run("kill -TERM $(pgrep -x surf)")
    if rc != 0:
        raise RuntimeError(f"could not send SIGTERM to surf: {stderr}")

    deadline = time.monotonic() + _DEADLINE_SECONDS
    after_samples = []
    while True:
        after_samples.append(probe())
        outcome, reason = verdict(before_sample, after_samples)
        if outcome == "restarted" or time.monotonic() >= deadline:
            break
        time.sleep(_POLL_SECONDS)

    if outcome == "error":
        raise RuntimeError(reason)
    assert outcome == "restarted", f"{outcome}: {reason}"
