# Bench smoke tier (#122): the wisekiosk-backend contract this pipeline
# proves on every candidate boot, re-hosting WiseKiosk's own smoke-native
# cases in Yocto's oeqa harness.

import time

from oeqa.runtime.case import OERuntimeTestCase

# TEST_SUITES = "wisekiosk" (includes/testimage.yaml) replaces, rather than
# extends, the default suite list, so the poky "ssh" module (and its
# ssh.SSHTest.test_ssh) is never loaded here; these four cases are independent
# and carry no OETestDepends chain to it or to each other.

# Busybox wget exits 0 only on a 2xx response, so `status == 0` below stands
# in for "got a good response" without reading a body or a status line.
HEALTHZ_URL = "http://127.0.0.1:8080/healthz"
INDEX_URL = "http://127.0.0.1:8080/"
# D-I's 60s reachability bound: the unit must be active before healthz can
# answer, so both cases poll the same window from case start.
BOUND_SECONDS = 60
POLL_INTERVAL_SECONDS = 2
# self.target.run()'s own default (SSHControl's 300s) is an IDLE timeout, not
# a total one, and a wedged-but-connected backend produces no output at all --
# so left unset, one poll attempt could itself block for up to 300s, well past
# BOUND_SECONDS. This bounds a single attempt well under that.
WGET_TIMEOUT_SECONDS = 10


class WiseKioskTest(OERuntimeTestCase):

    def test_backend_unit_active(self):
        deadline = time.time() + BOUND_SECONDS
        status, output = None, None
        while True:
            status, output = self.target.run("systemctl is-active wisekiosk.service")
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
            status, output = self.target.run("wget -q -O- %s" % HEALTHZ_URL, timeout=WGET_TIMEOUT_SECONDS)
            if status == 0:
                return
            if time.time() >= deadline:
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        self.fail("/healthz did not return within %ss (rc %s): %s" % (BOUND_SECONDS, status, output))

    def test_page_serves(self):
        status, output = self.target.run("wget -q -O- %s" % INDEX_URL, timeout=WGET_TIMEOUT_SECONDS)
        self.assertEqual(status, 0, "GET / failed (rc %s): %s" % (status, output))
        self.assertIn("<html", output, "GET / did not return an <html> body: %s" % output)

    def test_health_check_flag(self):
        status, output = self.target.run("/usr/bin/wisekiosk -health-check")
        if status != 0 and "flag provided but not defined" in output:
            self.skipTest("pinned app has no -health-check")
        self.assertEqual(status, 0, "-health-check failed (rc %s): %s" % (status, output))
