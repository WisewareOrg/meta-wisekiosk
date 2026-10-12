"""Switches the board between live and replay mode for one test's duration."""

import os
import tempfile
from pathlib import Path

from tenacity import Retrying, stop_after_delay, wait_fixed

from verdicts.mode import mode_token
from verdicts.perf import expected_state

_CONFIG_PATH = "/data/config/config.json"
_ENV_PATH = "/data/config/wisekiosk.conf"
_CA_DIR = "/data/config/replay-ca"
_CA_PATH = f"{_CA_DIR}/ca.crt"
_HOST_CA = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
_WAIT_TIMEOUT = 60
_WAIT_INTERVAL = 2


class Replay:
    """Switches the board into replay mode against one recorded set, then restores it.

    Holds the labgrid SSHDriver, the set's own directory and the proxy's loopback port. Every
    method is transport plus the pure `mode_token` judgement. `exit` undoes exactly what `enter`
    did, best effort past the first failure: every step runs even if an earlier one raised, and
    the first exception is re-raised once every step has run.
    """

    def __init__(self, driver, set_dir, port):
        """Bind one Replay to a board and the set it will switch that board into.

        Args:
            driver: A labgrid SSHDriver bound to the `main` target.
            set_dir (pathlib.Path): The replay set's own directory (holds `config.json` and
                `expected.json`).
            port (int): The runner's `proxy` fixture's own loopback port.
        """
        self._driver = driver
        self._set_dir = set_dir
        self._port = port
        self._saved_config_path = None

    @property
    def expected(self):
        """dict: the set's own `expected.json`, as `verdicts.perf.expected_state` validates it.

        Raises:
            ValueError: `expected.json` does not carry exactly `cards`, `faulted` and
                `unreachable`.
        """
        return expected_state((self._set_dir / "expected.json").read_text())

    def install_ca_if_needed(self):
        """Install the host's mitmproxy CA on the board, if absent or different.

        Raises:
            OSError: the host's own mitmproxy CA (`~/.mitmproxy/mitmproxy-ca-cert.pem`) does not
                exist -- the runner's `proxy` fixture must start mitmdump at least once first.
        """
        wanted = _HOST_CA.read_bytes()
        current = self._try_get(_CA_PATH)
        if current == wanted:
            return
        _stdout, stderr, rc = self._driver.run(f"mkdir -p {_CA_DIR}")
        if rc != 0:
            raise RuntimeError(f"could not create {_CA_DIR}: {stderr}")
        self._driver.put(str(_HOST_CA), _CA_PATH)
        _stdout, stderr, rc = self._driver.run(f"chmod 0644 {_CA_PATH}")
        if rc != 0:
            raise RuntimeError(f"could not chmod {_CA_PATH}: {stderr}")

    def enter(self):
        """Save the board's own `config.json`, switch it into replay mode, and confirm the switch.

        Raises:
            RuntimeError: a restart did not reach active, the board's own mode does not read
                "replay" afterward, or no `wisekiosk` process could be found to read it from.
        """
        self._saved_config_path = self._save(_CONFIG_PATH)
        env = (
            f"HTTPS_PROXY=http://127.0.0.1:{self._port}\n"
            f"SSL_CERT_FILE={_CA_PATH}\n"
            f"SSL_CERT_DIR={_CA_DIR}\n"
        )
        self._write_text(_ENV_PATH, env)
        self._driver.put(str(self._set_dir / "config.json"), _CONFIG_PATH)
        self._restart_into("replay")

    def exit(self):
        """Remove the env file, restore the saved `config.json`, and confirm the board is live.

        Best effort past the first failure: every step is attempted even if an earlier one
        raised; the first exception raised is re-raised once every step has run. The host-side
        saved copy of `config.json` is only deleted once it has actually been restored to the
        board -- if any step raised, the copy is kept and its path is named in the raised error,
        so the board can still be recovered by hand from it.

        Raises:
            Exception: the first exception any step raised, if any did. Its message names the
                kept host-side copy of `config.json` when one of the other steps is what failed.
        """
        steps = [
            lambda: self._driver.run(f"rm -f {_ENV_PATH}"),
            lambda: self._driver.put(str(self._saved_config_path), _CONFIG_PATH),
            lambda: self._restart_into("live"),
        ]
        first_error = None
        for step in steps:
            try:
                step()
            except Exception as exc:  # noqa: BLE001 -- collected, not swallowed
                if first_error is None:
                    first_error = exc
        if first_error is None:
            if self._saved_config_path is not None:
                self._saved_config_path.unlink(missing_ok=True)
        else:
            raise RuntimeError(
                f"{first_error} (the board's saved config.json is kept at "
                f"{self._saved_config_path})"
            ) from first_error

    def _restart_into(self, want_mode):
        """Restart the backend, confirm it reached `want_mode`, then restart the browser.

        Args:
            want_mode (str): The mode `_read_mode` must report after the restart (`"replay"` or
                `"live"`).

        Raises:
            RuntimeError: a restart did not exit 0, or the backend's own mode does not match
                `want_mode`.
        """
        _stdout, stderr, rc = self._driver.run("systemctl restart wisekiosk.service")
        if rc != 0:
            raise RuntimeError(f"could not restart wisekiosk.service: {stderr}")
        self._wait_active("wisekiosk.service")
        mode = self._read_mode()
        if mode != want_mode:
            raise RuntimeError(f"wisekiosk.service entered mode={mode!r}, expected {want_mode!r}")
        _stdout, stderr, rc = self._driver.run("systemctl restart kiosk.service")
        if rc != 0:
            raise RuntimeError(f"could not restart kiosk.service: {stderr}")

    def _read_mode(self):
        """The backend's own replay-mode token, read from `wisekiosk.service`'s own MainPID.

        Returns:
            str | None: `verdicts.mode.mode_token`'s own result.

        Raises:
            RuntimeError: `wisekiosk.service` has no MainPID, or its environ could not be read.
        """
        stdout, stderr, rc = self._driver.run(
            "systemctl show -p MainPID --value wisekiosk.service"
        )
        pid = "\n".join(stdout).strip()
        if rc != 0 or not pid or pid == "0":
            raise RuntimeError(f"wisekiosk.service has no MainPID: {stderr}")
        stdout, stderr, rc = self._driver.run(f"tr '\\0' '\\n' < /proc/{pid}/environ")
        if rc != 0:
            raise RuntimeError(f"could not read /proc/{pid}/environ: {stderr}")
        return mode_token("\n".join(stdout), self._port)

    def _wait_active(self, unit):
        """Poll `systemctl is-active` until `unit` reports active, or raise at the deadline.

        Args:
            unit (str): The systemd unit's own name.

        Raises:
            RuntimeError: `unit` did not reach `"active"` within `_WAIT_TIMEOUT` seconds.
        """
        for attempt in Retrying(
            stop=stop_after_delay(_WAIT_TIMEOUT), wait=wait_fixed(_WAIT_INTERVAL), reraise=True
        ):
            with attempt:
                stdout, _stderr, rc = self._driver.run(f"systemctl is-active {unit}")
                if rc != 0 or "".join(stdout).strip() != "active":
                    raise RuntimeError(f"{unit} not active yet")

    def _try_get(self, path):
        """The remote file's bytes, or None if it could not be read (e.g. absent).

        Args:
            path (str): The remote file's path on the board.

        Returns:
            bytes | None: `path`'s contents, or None if `path` could not be fetched.
        """
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "f"
            try:
                self._driver.get(path, str(local))
            except Exception:  # noqa: BLE001 -- "absent or unreadable" is one outcome, not an error
                return None
            return local.read_bytes()

    def _save(self, path):
        """scp `path` to a new host-side temp file and return that file's own path.

        Args:
            path (str): The remote file's path on the board.

        Returns:
            pathlib.Path: The new host-side temp file's own path, holding `path`'s contents.
        """
        fd, name = tempfile.mkstemp()
        os.close(fd)
        local = Path(name)
        self._driver.get(path, str(local))
        return local

    def _write_text(self, path, text):
        """Write `text` to `path` on the board, via a host-side temp file and `put`.

        Args:
            path (str): The remote destination path on the board.
            text (str): The content to write.
        """
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "f"
            local.write_text(text)
            self._driver.put(str(local), path)
