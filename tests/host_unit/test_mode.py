"""Specifies tests/verdicts/mode.py: the backend's replay-mode token, read from its own
`/proc/<pid>/environ` dump. No device, no file -- every environ dump is constructed.
"""

from verdicts.mode import mode_token


def test_mode_token_live_when_no_https_proxy_line():
    assert mode_token("PATH=/usr/bin\nHOME=/root\n", 8080) == "live"


def test_mode_token_live_on_empty_environ():
    assert mode_token("", 8080) == "live"


def test_mode_token_replay_on_exact_match():
    environ = "PATH=/usr/bin\nHTTPS_PROXY=http://127.0.0.1:8080\nHOME=/root\n"
    assert mode_token(environ, 8080) == "replay"


def test_mode_token_none_on_wrong_port():
    environ = "HTTPS_PROXY=http://127.0.0.1:8081\n"
    assert mode_token(environ, 8080) is None


def test_mode_token_none_on_a_non_loopback_proxy():
    # 203.0.113.0/24 is RFC 5737's documentation range -- never a real device address.
    environ = "HTTPS_PROXY=http://203.0.113.5:8080\n"
    assert mode_token(environ, 8080) is None


def test_mode_token_none_on_more_than_one_https_proxy_line():
    environ = "HTTPS_PROXY=http://127.0.0.1:8080\nHTTPS_PROXY=http://127.0.0.1:8080\n"
    assert mode_token(environ, 8080) is None
