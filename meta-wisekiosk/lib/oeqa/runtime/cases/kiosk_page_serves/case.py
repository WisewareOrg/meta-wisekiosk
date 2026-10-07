from kiosk.case import WiseKioskCase, INDEX_URL, POLL_ATTEMPT_TIMEOUT_SECONDS


class KioskPageServesTest(WiseKioskCase):

    def test_page_serves(self):
        status, output = self.target.run("wget -q -O- %s" % INDEX_URL, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        self.assertEqual(status, 0, "GET / failed (rc %s): %s" % (status, output))
        self.assertIn("<html", output, "GET / did not return an <html> body: %s" % output)
