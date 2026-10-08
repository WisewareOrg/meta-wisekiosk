import datetime
import os
import subprocess
import sys
import time
from pathlib import Path

from oeqa.runtime.case import OERuntimeTestCase

from . import probe, record

# busybox wget: rc 0 only on 2xx. kiosk_backend_unit, kiosk_healthz_bound and
# kiosk_page_serves import the ones they need from here -- one spelling of
# each literal, not a copy per case.
HEALTHZ_URL = "http://127.0.0.1:8080/healthz"
INDEX_URL = "http://127.0.0.1:8080/"
BOUND_SECONDS = 60
POLL_INTERVAL_SECONDS = 2
POLL_ATTEMPT_TIMEOUT_SECONDS = 10

# Walks the root's whole tree and reads every window's WM_NAME -- the one
# spelling every probe-reading case ran as its own copy. docs/testing.md §
# "The render and applied cases" has the why.
_WINDOW_TITLES_PROBE = (
    "for id in $(DISPLAY=:0 xwininfo -root -tree 2>/dev/null | "
    "awk '/^ +0x/ { print $1 }'); do "
    'DISPLAY=:0 xprop -id "$id" WM_NAME 2>/dev/null; done'
)

# The one probe script (design §2.5: "one probe script, one record
# format"), owned by kiosk_applied -- deployed from here, never duplicated.
_PROBE_SRC = Path(__file__).resolve().parents[1] / "cases" / "kiosk_applied" / "probe.js"


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
    call against the host checkout); every judgement is a call into
    record.py.
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
        hmac_key_env = (cls.td or {}).get("KIOSK_HMAC_KEY") or os.environ.get("KIOSK_HMAC_KEY")
        if not role or not hostname or not hmac_key_env:
            raise RuntimeError(
                "KIOSK_TARGET_ROLE, KIOSK_TARGET_HOSTNAME and KIOSK_HMAC_KEY must all be "
                "set -- under testimage this is includes/testimage.yaml's env passthrough; "
                "by hand, tools/oe-test.sh resolves them from local/device-identity.md and "
                "<repo>/local/keys/hmac.key")

        # The key's path is an input, like role and hostname, never
        # derived from __file__: inside kas-container that resolves to
        # the /repo mount, a different one from PIPELINE_KEYS_DIR's
        # /work/local/keys (tools/kas-run.sh).
        repo = Path(__file__).resolve().parents[5]
        hmac_key_path = Path(hmac_key_env)
        if not hmac_key_path.is_file():
            raise RuntimeError(f"no {hmac_key_path} -- run 'just pipeline-install' first")

        # cls.tc.target, not cls.target: OERuntimeTestLoader sets the
        # latter per test-case instance, not on the class.
        target = cls.tc.target

        # The bench-only refusal: the first thing this suite does with the
        # device, before any other collector.
        observed_hostname = target.run("hostname")[1].strip()
        mismatch = record.hostname_mismatch(observed_hostname, hostname)
        if mismatch:
            raise RuntimeError(mismatch)

        WiseKioskCase.role = role
        WiseKioskCase.hmac_key = hmac_key_path.read_bytes()

        start = _now_iso()
        tool_commit, dirty = _tool_commit_and_dirty(repo)
        argv = record.scrub_argv(sys.argv, target.ip)

        boot_id = target.run("cat /proc/sys/kernel/random/boot_id")[1].strip()
        rauc_shell = target.run("rauc status --detailed --output-format=shell")[1]
        slot = record.booted_slot(rauc_shell)
        installed_at = record.slot_installed_at(rauc_shell)

        # Every boot's own slot and the instant that boot logged it, one
        # call, not one per boot and never --list-boots' first_entry: the
        # early-boot clock floors first_entry on some boots before NTP
        # syncs, while rauc.service's own "Booted into rootfs.<n> (<slot>)"
        # line is stamped after the clock is restored. docs/testing.md §
        # "Running it" has the why.
        boot_journal_lines = target.run(
            "journalctl -u rauc.service -o json "
            "--output-fields=_BOOT_ID,MESSAGE,__REALTIME_TIMESTAMP")[1]
        boot_ordinal = record.boot_ordinal(boot_journal_lines, installed_at, slot)
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

    def arm_probe(self):
        """Deploys kiosk_applied's probe.js and restarts kiosk.service so
        the freshly-deployed script is the one surf runs next -- the
        mkdir/copyTo/restart sequence every probe-reading case repeated as
        its own copy. Registers the script's own removal as this test's
        cleanup."""
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")
        mkdir_status, _ = self.target.run(
            "mkdir -p /home/root/.surf", timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        if mkdir_status != 0:
            raise RuntimeError("could not arm the probe (mkdir)")
        self.target.copyTo(str(_PROBE_SRC), "/home/root/.surf/script.js")
        restart_status, _ = self.target.run("systemctl restart kiosk.service")
        if restart_status != 0:
            raise RuntimeError("could not restart kiosk.service to arm the probe")

    def titles(self):
        """The device's window titles, through xprop's WM_NAME walk --
        transport only, raw text. Each case's own verdict module parses it
        (framework.probe.title_lines, then its own field contract)."""
        _status, output = self.target.run(
            _WINDOW_TITLES_PROBE, timeout=POLL_ATTEMPT_TIMEOUT_SECONDS)
        return output

    def wait_applied(self, seconds):
        """Polls self.titles() until some window's probe payload reports
        state=applied, raising with the last known state if seconds
        elapses first. Only the state field is required here -- the
        stricter, all-five-fields contract stays kiosk_applied.verdict's
        own (a judgment call: flagged, not silent)."""
        deadline = time.time() + seconds
        last = "no probe payload"
        while True:
            for title in probe.title_lines(self.titles()):
                found = probe.fields(title)
                if found is not None and "state" in found:
                    last = found["state"]
                    if last == "applied":
                        return
            if time.time() >= deadline:
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        raise RuntimeError(f"the page did not apply within {seconds}s (last: {last})")
