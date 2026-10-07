from oeqa.runtime.cases.kiosk.case import WiseKioskCase


class KioskHealthFlagTest(WiseKioskCase):

    def test_health_check_flag(self):
        status, output = self.target.run("/usr/bin/wisekiosk -health-check")
        if status != 0 and "flag provided but not defined" in output:
            self.skipTest("pinned app has no -health-check")
        self.assertEqual(status, 0, "-health-check failed (rc %s): %s" % (status, output))
