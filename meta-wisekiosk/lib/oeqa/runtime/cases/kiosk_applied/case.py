import tempfile
import time
from pathlib import Path

from framework import record
from framework.base import WiseKioskCase, POLL_ATTEMPT_TIMEOUT_SECONDS

from .verdict import read_sample, verdict as applied_verdict

_KIOSK_CONF_PATH = "/data/config/kiosk.conf"
_KIOSK_CONF_BACKUP = "/data/config/kiosk.conf.seeded-fail-bak"
_KIOSK_URL_KEY = "KIOSK_URL"
_SEEDED_URL_LINE = f"{_KIOSK_URL_KEY}=http://localhost:1"

_PROBE_SRC = Path(__file__).resolve().parent / "probe.js"

_APPLIED_DEADLINE_SECONDS = 90
_APPLIED_POLL_SECONDS = 2
_APPLIED_ATTEMPTS = 2


class KioskAppliedTest(WiseKioskCase):

    def _read_applied_sample(self):
        return read_sample(self.titles())

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
            outcome = applied_verdict(samples)
            if outcome == "applied":
                return outcome, samples[-1]
            if time.time() >= deadline:
                break
            time.sleep(_APPLIED_POLL_SECONDS)

        outcome = applied_verdict(samples)
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

    def _restore_kiosk_conf(self):
        # Idempotent: a backup already consumed by an earlier restore in
        # this same method leaves nothing to do.
        status, _ = self.target.run(f"test -f {_KIOSK_CONF_BACKUP}")
        if status != 0:
            return
        self.target.run(f"mv {_KIOSK_CONF_BACKUP} {_KIOSK_CONF_PATH}")
        self.target.run("systemctl restart kiosk.service")

    def test_applied_seeded_fail(self):
        if WiseKioskCase.role != "bench":
            raise RuntimeError(
                f"test_applied_seeded_fail requires role=bench, got {WiseKioskCase.role!r}")
        self.addCleanup(self.target.run, "rm -f /home/root/.surf/script.js")
        self.addCleanup(self._restore_kiosk_conf)

        status, original = self.target.run(f"cat {_KIOSK_CONF_PATH}")
        if status != 0:
            raise RuntimeError(f"could not read {_KIOSK_CONF_PATH}")
        backup_status, _ = self.target.run(f"cp {_KIOSK_CONF_PATH} {_KIOSK_CONF_BACKUP}")
        if backup_status != 0:
            raise RuntimeError(f"could not back up {_KIOSK_CONF_PATH}")

        seeded_lines = [line for line in original.splitlines()
                        if not line.startswith(_KIOSK_URL_KEY + "=")]
        seeded_lines.append(_SEEDED_URL_LINE)
        seeded = "\n".join(seeded_lines) + "\n"
        with tempfile.NamedTemporaryFile("w", suffix=".conf") as seeded_file:
            seeded_file.write(seeded)
            seeded_file.flush()
            self.target.copyTo(seeded_file.name, _KIOSK_CONF_PATH)

        outcome, _sample = self._applied_attempt()
        if outcome != "failed:error:not-app":
            self.fail(f"seeded KIOSK_URL did not fail as failed:error:not-app -- got {outcome!r}")

        self._restore_kiosk_conf()

        outcome, _sample = self._applied_attempt()
        if outcome != "applied":
            self.fail(f"did not return to applied after restoring kiosk.conf -- got {outcome!r}")
