import time

from kiosk.case import (
    WiseKioskCase, BOUND_SECONDS, POLL_INTERVAL_SECONDS, POLL_ATTEMPT_TIMEOUT_SECONDS,
)


class KioskBackendUnitTest(WiseKioskCase):

    def test_backend_unit_active(self):
        deadline = time.time() + BOUND_SECONDS
        status, output = None, None
        while True:
            status, output = self.target.run(
                "systemctl is-active wisekiosk.service", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
            if output == "active":
                return
            if time.time() >= deadline:
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        self.fail("wisekiosk.service was not active within %ss (rc %s): %s" % (BOUND_SECONDS, status, output))
