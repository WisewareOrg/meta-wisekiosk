import datetime
import os
import subprocess
import sys
import time
from pathlib import Path

from oeqa.runtime.case import OERuntimeTestCase

from wisekiosk import applied, record, render

# busybox wget: rc 0 only on 2xx
HEALTHZ_URL = "http://127.0.0.1:8080/healthz"
INDEX_URL = "http://127.0.0.1:8080/"
BOUND_SECONDS = 60
POLL_INTERVAL_SECONDS = 2
POLL_ATTEMPT_TIMEOUT_SECONDS = 10

# The render check's default crop, ported from tools/kiosk-render-check.sh --
# docs/testing.md § "The render and applied cases" has the why.
_RENDER_CROP = "560x300+220+20"
_RENDER_PROBE = (
    'if ! command -v import > /dev/null 2>&1; then echo "cap import=0"; exit 0; fi\n'
    "F=/tmp/render-check.$$\n"
    "grab() {\n"
    "    n=$1\n"
    '    DISPLAY=:0 import -window root -crop "%s" +repage "$F.$n.png" > /dev/null 2>"$F.$n.err"\n'
    "    rc=$?\n"
    '    if [ -f "$F.$n.png" ]; then\n'
    '        b=$(wc -c < "$F.$n.png")\n'
    '        m=$(md5sum < "$F.$n.png" | cut -d\' \' -f1)\n'
    "    else\n"
    "        b=0\n"
    "        m=none\n"
    "    fi\n"
    '    err=$(tr \'\\n\' \' \' < "$F.$n.err" 2>/dev/null | tr -s \' \' \'_\')\n'
    '    echo "frame $n rc=$rc bytes=$b md5=$m err=${err:-none}"\n'
    "}\n"
    "grab 1\n"
    "sleep 3\n"
    "grab 2\n"
    'if command -v identify > /dev/null 2>&1 && [ -f "$F.2.png" ]; then\n'
    "    identify -format 'blank min=%%[fx:minima*255] max=%%[fx:maxima*255] "
    "mean=%%[fx:mean*255]\\n' \"$F.2.png\" 2>/dev/null\n"
    "fi\n"
    'rm -f "$F.1.png" "$F.2.png" "$F.1.err" "$F.2.err"\n'
) % _RENDER_CROP

# Walks the root's whole tree and reads every window's WM_NAME.
# docs/testing.md § "The render and applied cases" has the why.
_WINDOW_TITLES_PROBE = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | "
    "awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)

_PROBE_SRC = Path(__file__).resolve().parents[3] / "wisekiosk" / "applied" / "probe.js"

_APPLIED_DEADLINE_SECONDS = 90
_APPLIED_POLL_SECONDS = 2
_APPLIED_ATTEMPTS = 2


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _tool_commit_and_dirty(repo):
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    porcelain = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True).stdout
    return commit, record.dirty(porcelain)


class WiseKioskCase(OERuntimeTestCase):
    """Writes the run record once per run, into
    self.tc.extraresults["wisekiosk.record"] (docs/testing.md names what it
    carries, where it lands and the posting precondition), before any
    case's own assertions run. Transport only: every collector here is a
    self.target.run of a busybox one-liner (or, for the tool line, a git
    call against the host checkout); every judgement is a call into the
    wisekiosk package.
    """

    @classmethod
    def setUpClass(cls):
        if not hasattr(cls.tc, "extraresults"):
            cls.tc.extraresults = {}
        record_dict = cls.tc.extraresults.setdefault(record.RECORD_KEY, {})
        if "tool" in record_dict:
            return

        role = (cls.td or {}).get("KIOSK_TARGET_ROLE") or os.environ.get("KIOSK_TARGET_ROLE")
        hostname = (cls.td or {}).get("KIOSK_TARGET_HOSTNAME") or os.environ.get("KIOSK_TARGET_HOSTNAME")
        if not role or not hostname:
            raise RuntimeError(
                "KIOSK_TARGET_ROLE and KIOSK_TARGET_HOSTNAME must both be set -- "
                "under testimage this is includes/testimage.yaml's env passthrough; "
                "by hand, tools/oe-test.sh resolves them from local/device-identity.md")

        repo = Path(__file__).resolve().parents[5]
        hmac_key_path = repo / "local" / "keys" / "hmac.key"
        if not hmac_key_path.is_file():
            raise RuntimeError(f"no {hmac_key_path} -- run 'just pipeline-install' first")

        # cls.tc.target, not cls.target: OERuntimeTestLoader sets the
        # latter per test-case instance, not on the class.
        target = cls.tc.target

        # The bench-only refusal: the first thing this suite does with the
        # device, before any other collector.
        observed_hostname = target.run("hostname")[1].strip()
        if observed_hostname != hostname:
            raise RuntimeError(
                f"the board's live hostname ({observed_hostname!r}) does not match "
                f"the expected KIOSK_TARGET_HOSTNAME ({hostname!r}) -- refusing to "
                "run against a board this suite did not expect")

        WiseKioskCase.role = role
        WiseKioskCase.hmac_key = hmac_key_path.read_bytes()

        start = _now_iso()
        tool_commit, dirty = _tool_commit_and_dirty(repo)
        argv = record.scrub_argv(sys.argv, target.ip)

        boot_id = target.run("cat /proc/sys/kernel/random/boot_id")[1].strip()
        rauc_shell = target.run("rauc status --detailed --output-format=shell")[1]
        slot = record.booted_slot(rauc_shell)
        installed_at = record.slot_installed_at(rauc_shell)
        boots_json = target.run("journalctl --list-boots -o json")[1]

        # Every boot's own slot, one call, not one per boot: rauc.service's
        # own "Booted into rootfs.<n> (<slot>)" line survives the early-boot
        # journal rotation that drops the kernel's Command line entry.
        # docs/testing.md § "Running it" has the why.
        boot_journal_lines = target.run(
            "journalctl -u rauc.service -o json --output-fields=_BOOT_ID,MESSAGE")[1]
        boot_slots = record.boot_slots_from_journal(boot_journal_lines)
        boot_ordinal = record.boot_ordinal(boots_json, installed_at, slot, boot_slots)
        uptime_s = record.uptime_seconds(target.run("cat /proc/uptime")[1])

        WiseKioskCase.board_fields = {
            "role": role, "boot_id": boot_id, "boot_ordinal": boot_ordinal,
            "uptime_s": uptime_s, "start": start,
        }

        buildinfo = target.run("cat /etc/buildinfo")[1]
        sha = record.parse_buildinfo(buildinfo)

        index_html = target.run("wget -qO- %s" % INDEX_URL)[1]
        bundle = ",".join(record.asset_hashes(index_html))

        # hexdump, not cat: busybox has no base64 applet and no long-option
        # od, and a hex dump is the byte-safe transport the keyed hash
        # needs. docs/testing.md § "Running it" has the why.
        config_hex = target.run("hexdump -ve '1/1 \"%02x\"' /data/config/config.json")[1]
        config_json = record.decode_hex_dump(config_hex).decode()
        config_mac = record.keyed_hash(WiseKioskCase.hmac_key, config_json.encode())
        config = record.config_summary(config_json)

        pid = record.pid_from_pgrep(target.run("pgrep -x surf")[1])
        browser = target.run("cat /proc/%s/comm" % pid)[1].strip()
        nrestarts = target.run(
            "systemctl show -p NRestarts --value kiosk.service")[1].strip()
        cmdline_sha = target.run(
            "sha256sum /proc/%s/cmdline | cut -d' ' -f1" % pid)[1].strip()
        webkit_env = record.webkit_env(
            target.run("tr '\\0' '\\n' < /proc/%s/environ" % pid)[1])
        conf_status, kiosk_conf_hex = target.run("hexdump -ve '1/1 \"%02x\"' /data/config/kiosk.conf")
        kiosk_conf_mac = record.kiosk_conf_mac(
            conf_status, record.decode_hex_dump(kiosk_conf_hex).decode(), WiseKioskCase.hmac_key)
        mode = target.run("DISPLAY=:0 xrandr | awk '/\\*/{print $1; exit}'")[1].strip()
        kernel = target.run("uname -r")[1].strip()
        cpufreq_max = target.run(
            "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq")[1].strip()
        timesync = target.run("timedatectl show -p NTPSynchronized --value")[1].strip()

        tool_name = record.tool_name(sys.argv[0])
        record_dict["tool"] = record.tool_line(
            name=tool_name, tool_commit=tool_commit, dirty=dirty, argv=argv)
        record_dict["board"] = record.board_line(end=_now_iso(), **WiseKioskCase.board_fields)
        record_dict["image"] = record.image_line(sha=sha, slot=slot)
        record_dict["app"] = record.app_line(bundle=bundle, config_mac=config_mac, config=config)
        record_dict["sut"] = record.sut_line(
            browser=browser, nrestarts=nrestarts, cmdline_sha=cmdline_sha,
            webkit_env=webkit_env, kiosk_conf_mac=kiosk_conf_mac, mode=mode,
            kernel=kernel, cpufreq_max=cpufreq_max, timesync=timesync)

    def tearDown(self):
        super().tearDown()
        self.tc.extraresults[record.RECORD_KEY]["board"] = record.board_line(
            end=_now_iso(), **WiseKioskCase.board_fields)


class WiseKioskTest(WiseKioskCase):

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

    def test_render_advancing(self):
        _status, output = self.target.run(_RENDER_PROBE)
        outcome, reason = render.verdict(output.splitlines())
        if outcome == "advancing":
            return
        if outcome == "frozen":
            self.fail(reason)
        raise RuntimeError(reason)

    def _read_applied_sample(self):
        status, output = self.target.run(
            _WINDOW_TITLES_PROBE, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if status != 0:
            return None
        return applied.read_sample(output)

    def _applied_attempt(self):
        # A deploy failure here takes the same retry path as a probe
        # failure: the caller only ever sees an "error:*" outcome. Deploy
        # (mkdir, copyTo) runs before the clock and is unbounded; the 90 s
        # deadline starts when the restart is issued, matching the
        # ticket's "applied within 90 s of the restart" -- the restart's
        # own duration counts, and the poll gets the remainder.
        try:
            mkdir_status, _ = self.target.run(
                "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
            if mkdir_status != 0:
                return "error:deploy", None
            self.target.copyTo(str(_PROBE_SRC), "/home/root/.surf/script.js")
            deadline = time.time() + _APPLIED_DEADLINE_SECONDS
            restart_status, _ = self.target.run(
                "systemctl restart kiosk.service", timeout=int(max(1, deadline - time.time())))
            if restart_status != 0:
                return "error:deploy", None
        except AssertionError:
            return "error:deploy", None

        samples = []
        while True:
            samples.append(self._read_applied_sample())
            outcome = applied.verdict(samples)
            if outcome == "applied":
                return outcome, samples[-1]
            if time.time() >= deadline:
                break
            time.sleep(_APPLIED_POLL_SECONDS)

        outcome = applied.verdict(samples)
        real = [sample for sample in samples if sample is not None]
        return outcome, (real[-1] if real else None)

    def test_page_applied(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_page_applied requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")

        outcome, sample = None, None
        for attempt in range(_APPLIED_ATTEMPTS):
            outcome, sample = self._applied_attempt()
            if not outcome.startswith("error:"):
                break
        else:
            # The declared transport kind: run.sh's own infrastructure-
            # failure path reads this exact state from the page line.
            self.tc.extraresults[record.RECORD_KEY][f"page.{self.id()}"] = record.page_line(
                nonce="", state=record.TRANSPORT_STATE, cards="-/-", faulted=0, unreachable=0)
            raise RuntimeError(f"transport: {outcome} after {_APPLIED_ATTEMPTS} attempts")

        self.tc.extraresults[record.RECORD_KEY][f"page.{self.id()}"] = record.page_line(
            nonce=sample["nonce"], state=sample["state"], cards=sample["cards"],
            faulted=sample["faulted"], unreachable=sample["unreachable"])

        if outcome == "applied":
            return
        self.fail(outcome)
