import time

from framework.base import (
    WiseKioskCase, HEALTHZ_URL, BOUND_SECONDS, POLL_INTERVAL_SECONDS, POLL_ATTEMPT_TIMEOUT_SECONDS,
)


class KioskHealthzBoundTest(WiseKioskCase):

    def test_healthz_within_bound(self):
        deadline = time.time() + BOUND_SECONDS
        status, output = None, None
        while True:
            status, output = self.target.run("wget -q -O- %s" % HEALTHZ_URL, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
            if status == 0:
                return
            if time.time() >= deadline:
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        self.fail("/healthz did not return within %ss (rc %s): %s" % (BOUND_SECONDS, status, output))
