"""Target suite: the instance's own HTTPS fetches, proved against a replayed recording."""

import contextlib
import time
from pathlib import Path

import pytest

from page import BOUND_SECONDS

SET_DIR = Path(__file__).resolve().parent.parent / "replay" / "sets" / "cards4-live"
CA_PATH = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"

_CA_BOARD_PATH = "/tmp/replay-ca.pem"
_DROP_IN_PATH = "/run/systemd/system/wisekiosk.service.d/replay.conf"


@pytest.fixture
def replay_window(target, proxy, set_config, request):
    """Put the backend behind `proxy` for this test's duration, and return the browser start.

    Opens an `ssh -R` tunnel to the proxy's own loopback port, copies the proxy's CA to the
    board, writes a drop-in that points wisekiosk.service at the proxy through `HTTPS_PROXY`
    and adds the proxy's CA to its trust through `SSL_CERT_FILE`, then hands `set_config` the
    set's config.json -- whose own backend restart puts the backend onto the proxy before the
    browser starts. Teardown undoes each of this fixture's own steps in exactly the reverse
    order, then set_config's, then proxy's.

    Args:
        target (labgrid.Target): names the board's SSHDriver.
        proxy (wisebench.proxy.Proxy): the running proxy this test replays through.
        set_config (Callable[[str | os.PathLike], None]): swaps the board onto a config file.
        request (pytest.FixtureRequest): registers each step's undo.

    Returns:
        float: `time.monotonic()` taken once `set_config`'s `apply` has returned from starting
        `kiosk.service` -- the browser's start.
    """
    driver = target.get_driver("SSHDriver")

    stack = contextlib.ExitStack()
    request.addfinalizer(stack.close)
    stack.enter_context(driver.forward_remote_port(proxy.port, proxy.port))

    driver.put(str(CA_PATH), _CA_BOARD_PATH)

    def _remove_ca():
        _, _, returncode = driver.run(f"rm -f {_CA_BOARD_PATH}")
        assert returncode == 0, "could not remove the replay CA"

    request.addfinalizer(_remove_ca)

    _, _, returncode = driver.run(
        "mkdir -p /run/systemd/system/wisekiosk.service.d && "
        f"printf '[Service]\\nEnvironment=HTTPS_PROXY=http://127.0.0.1:{proxy.port}\\n"
        f"Environment=SSL_CERT_FILE={_CA_BOARD_PATH}\\n' > {_DROP_IN_PATH} && "
        "systemctl daemon-reload"
    )
    assert returncode == 0, "could not write the replay drop-in"

    def _remove_drop_in():
        _, _, returncode = driver.run(f"rm -f {_DROP_IN_PATH} && systemctl daemon-reload")
        assert returncode == 0, "could not remove the replay drop-in"

    request.addfinalizer(_remove_drop_in)

    set_config(SET_DIR / "config.json")
    return time.monotonic()


@pytest.mark.parametrize("proxy", [str(SET_DIR / "flows.har")], indirect=True)
def test_instance_reaches_out(proxy, replay_window, record_property):
    """The instance's own HTTPS fetches are answered from the recording, none unanswered.

    Both halves are read once BOUND_SECONDS have passed since the browser start.
    """
    record_property("requirement", "TST010")

    deadline = replay_window + BOUND_SECONDS
    time.sleep(max(0, deadline - time.monotonic()))

    served = proxy.served()
    unserved = [url for (_method, url), count in served.items() if count == 0]
    assert not unserved, f"never served from the recording: {unserved}"

    killed = proxy.killed()
    assert not killed, f"killed, not served from the recording: {killed}"
