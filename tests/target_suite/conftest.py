"""Fixtures shared by the target suite: the DOM probe, the replay-mode switch, and the device
context every test's report carries. Everything that names the application under test lives
here and in the modules beside it (`probe.py`, `replay.py`) -- the runner itself never learns it.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from framework.record import decode_hex_dump, keyed_hash
from probe import Probe
from replay import Replay
from runcmd import run_text
from verdicts.context import (
    asset_hashes,
    config_summary,
    kiosk_conf_mac,
    pid_from_pgrep,
    uptime_seconds,
    webkit_env,
)
from verdicts.layout import current_mode

_REPLAY_SETS_DIR = Path(__file__).resolve().parents[1] / "replay" / "sets"
_HMAC_KEY_PATH = Path(__file__).resolve().parents[2] / "local" / "keys" / "hmac.key"


def pytest_generate_tests(metafunc):
    """Indirectly parametrize the runner's `proxy` fixture with this run's replay set.

    `BENCH_SET` names the set directory under `tests/replay/sets/`; which set to replay is this
    layer's own choice, never the runner's. Required whenever this session collects
    `test_perf_window` -- `docs/testing.md` §"Running a candidate through bench test" states so.

    Args:
        metafunc: pytest's own hook argument; supplies the fixtures a test item requests.

    Raises:
        KeyError: `BENCH_SET` is unset entirely (a hand run that did not export it; `bench test`
            always sets it, to the empty string when `--set` is not given).
    """
    if "proxy" not in metafunc.fixturenames:
        return
    har = _REPLAY_SETS_DIR / os.environ["BENCH_SET"] / "flows.har"
    metafunc.parametrize("proxy", [str(har)], indirect=True, ids=[os.environ["BENCH_SET"]])


@pytest.fixture
def probe(target):
    """Deploy `probe.js`, restart the browser, and yield a reader for its latest window titles.

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.

    Yields:
        Callable[[], str]: Call it to read the board's current window titles, raw
            (`Probe.titles`'s own result) -- each test parses what it needs from it.
    """
    driver = target.get_driver("SSHDriver")
    deployed = Probe(driver)
    deployed.deploy()
    deployed.restart_browser()
    try:
        yield deployed.titles
    finally:
        deployed.remove()


@pytest.fixture
def replay_window(target, proxy):
    """Switch the board into replay mode for this test's duration, then restore it.

    Opens the reverse forward on the `proxy` fixture's own port, installs the replay CA if
    needed, performs the switch, and restores the board to live mode on teardown, including
    when `enter` itself fails partway through.

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.
        proxy (int): The runner's `proxy` fixture; its own loopback port.

    Yields:
        dict: The replay set's own `expected.json`.
    """
    driver = target.get_driver("SSHDriver")
    set_dir = _REPLAY_SETS_DIR / os.environ["BENCH_SET"]
    replay = Replay(driver, set_dir, proxy)
    with driver.forward_remote_port(proxy, proxy):
        replay.install_ca_if_needed()
        try:
            replay.enter()
        except Exception:
            replay.exit()
            raise
        try:
            yield replay.expected
        finally:
            replay.exit()


@pytest.fixture(scope="session")
def _device_facts(target):
    """Read the board's own context once per session: everything but `board`'s `end`.

    `record_property` is function-scoped, so a session-scoped fixture cannot call it directly
    (pytest's own scope rule) -- this fixture reads the board once; the function-scoped,
    autouse `device_context` fixture below attaches these facts, plus a fresh `end`, to every
    test's own report.

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.

    Returns:
        dict: One key per fact; see `docs/testing.md`'s `device_context` key list for the names.
    """
    driver = target.get_driver("SSHDriver")
    start = datetime.now(timezone.utc).isoformat()

    boot_id = run_text(driver, "cat /proc/sys/kernel/random/boot_id").strip()
    uptime_s = uptime_seconds(run_text(driver, "cat /proc/uptime"))

    index_html = run_text(driver, "wget -qO- http://127.0.0.1:8080/")
    bundle = ",".join(asset_hashes(index_html))

    hmac_key = _HMAC_KEY_PATH.read_bytes()
    config_hex = run_text(driver, 'hexdump -ve \'1/1 "%02x"\' /data/config/config.json')
    config_json = decode_hex_dump(config_hex).decode()
    config_mac = keyed_hash(hmac_key, config_json.encode())
    config = config_summary(config_json)

    pid = pid_from_pgrep(run_text(driver, "pgrep -x surf"))
    browser = run_text(driver, f"cat /proc/{pid}/comm").strip()
    nrestarts = run_text(driver, "systemctl show -p NRestarts --value kiosk.service").strip()
    cmdline_sha = run_text(driver, f"sha256sum /proc/{pid}/cmdline | cut -d' ' -f1").strip()
    webkit_environ = webkit_env(run_text(driver, f"tr '\\0' '\\n' < /proc/{pid}/environ"))
    conf_stdout, _conf_stderr, conf_rc = driver.run(
        'hexdump -ve \'1/1 "%02x"\' /data/config/kiosk.conf'
    )
    kiosk_conf_mac_token = kiosk_conf_mac(
        conf_rc, decode_hex_dump("\n".join(conf_stdout)).decode(), hmac_key
    )
    mode = current_mode(run_text(driver, "DISPLAY=:0 xrandr"))
    kernel = run_text(driver, "uname -r").strip()
    cpufreq_max = run_text(
        driver, "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
    ).strip()
    timesync = run_text(driver, "timedatectl show -p NTPSynchronized --value").strip()

    return {
        "start": start,
        "boot_id": boot_id,
        "uptime_s": uptime_s,
        "bundle": bundle,
        "config_mac": config_mac,
        "config": config,
        "browser": browser,
        "nrestarts": nrestarts,
        "cmdline_sha": cmdline_sha,
        "webkit_env": webkit_environ,
        "kiosk_conf_mac": kiosk_conf_mac_token,
        "mode": mode,
        "kernel": kernel,
        "cpufreq_max": cpufreq_max,
        "timesync": timesync,
    }


@pytest.fixture(autouse=True)
def device_context(_device_facts, record_property):
    """Attach the board's own device context to every test's report, one key per fact.

    Args:
        _device_facts (dict): This session's cached board/app/sut facts.
        record_property: pytest's own fixture; attaches each fact under its own key.
    """
    for key, value in _device_facts.items():
        record_property(key, value)
    yield
    record_property("end", datetime.now(timezone.utc).isoformat())
