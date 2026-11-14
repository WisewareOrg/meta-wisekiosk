"""Where the recorded replay set and the proxy's CA sit on the test host."""

from pathlib import Path

CARDS4_LIVE = Path(__file__).resolve().parent.parent / "replay" / "sets" / "cards4-live"
CA_PATH = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
