import time

from oeqa.runtime.case import OERuntimeTestCase

# busybox wget: rc 0 only on 2xx
HEALTHZ_URL = "http://127.0.0.1:8080/healthz"
INDEX_URL = "http://127.0.0.1:8080/"
BOUND_SECONDS = 60
POLL_INTERVAL_SECONDS = 2
POLL_ATTEMPT_TIMEOUT_SECONDS = 10


class WiseKioskTest(OERuntimeTestCase):

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

    def test_page_serves(self):
        status, output = self.target.run("wget -q -O- %s" % INDEX_URL, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        self.assertEqual(status, 0, "GET / failed (rc %s): %s" % (status, output))
        self.assertIn("<html", output, "GET / did not return an <html> body: %s" % output)

    def test_health_check_flag(self):
        status, output = self.target.run("/usr/bin/wisekiosk -health-check")
        if status != 0 and "flag provided but not defined" in output:
            self.skipTest("pinned app has no -health-check")
        self.assertEqual(status, 0, "-health-check failed (rc %s): %s" % (status, output))
