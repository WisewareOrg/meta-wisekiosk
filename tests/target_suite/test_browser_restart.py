"""TST005: the browser-restart check, judged by `verdicts.browser_restart`."""

import time

from probe import APPLIED_WAIT_SECONDS, wait_applied
from verdicts.applied import read_sample
from verdicts.browser_restart import verdict

_DEADLINE_SECONDS = 60
_POLL_SECONDS = 2


def test_browser_restart(target, probe):
    """TST005: once the browser dies, it comes back on its own and re-applies the page.

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.
        probe: deploys `probe.js` and restarts the browser; yields a reader for the board's
            current window titles, raw.
    """
    driver = target.get_driver("SSHDriver")
    before_sample = wait_applied(probe, APPLIED_WAIT_SECONDS)

    stdout, stderr, rc = driver.run("pgrep -x surf")
    if rc != 0 or not stdout:
        raise RuntimeError(f"surf is not running before the kill: {stderr}")
    _stdout, stderr, rc = driver.run("kill -TERM $(pgrep -x surf)")
    if rc != 0:
        raise RuntimeError(f"could not send SIGTERM to surf: {stderr}")

    deadline = time.monotonic() + _DEADLINE_SECONDS
    after_samples = []
    while True:
        after_samples.append(read_sample(probe()))
        outcome, reason = verdict(before_sample, after_samples)
        if outcome == "restarted" or time.monotonic() >= deadline:
            break
        time.sleep(_POLL_SECONDS)

    if outcome == "error":
        raise RuntimeError(reason)
    assert outcome == "restarted", f"{outcome}: {reason}"
