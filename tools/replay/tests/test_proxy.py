"""Specifies the pure parts of tools/replay/proxy.py -- the match-key builder, manifest load,
hash check, expiry refusal, leaf-last-month refusal, the MISS-to-502 decision, and the access-log
line it produces. No socket, no subprocess, no live `openssl` call: every certificate-shaped input
here is a string literal captured once from a real `openssl x509 -enddate -noout` run, every
CONNECT/HTTP shape a string literal captured once from a real `curl --proxy` round trip through a
throwaway TLS listener. ~/.claude/plans/202/step5/tests-notes.md records how each was produced.

`decide()`'s no-upstream-socket guarantee is structural here, not mocked: the test calls it with a
plain dict and asserts on the return value, importing nothing that could open a connection.
"""
from datetime import date, datetime

import pytest

from proxy import (
    Decision,
    LeafExpiringSoon,
    ReplaySetExpired,
    check_expiry,
    check_leaf_freshness,
    decide,
    hash_matches,
    load_manifest,
    match_key,
    parse_cert_enddate,
)

# A real CONNECT + decrypted inner request, captured from curl through a throwaway TLS listener
# standing in for the proxy (notes.md "Real artefacts"):
#   CONNECT example.invalid:443 HTTP/1.1
#   GET /weather?lat=1&lon=2 HTTP/1.1
#   Host: example.invalid
REAL_METHOD = "GET"
REAL_HOST = "example.invalid"
REAL_TARGET = "/weather?lat=1&lon=2"
REAL_KEY = "GET example.invalid /weather?lat=1&lon=2"

# A real response body and its real `sha256sum` digest (notes.md "Real artefacts").
REAL_BODY = b'{"temp_f": 72}'
REAL_BODY_SHA256 = "29391421140e7b282859469000378165c4c960a86077064929a089d71fd1061c"

# A real `openssl x509 -enddate -noout` line, captured from a real ECDSA leaf this agent generated.
REAL_ENDDATE_LINE = "notAfter=Oct  9 06:42:51 2027 GMT"


# ------------------------------------------------------------------------- match_key

def test_match_key_builds_method_host_target_from_the_real_captured_request():
    assert match_key(REAL_METHOD, REAL_HOST, REAL_TARGET) == REAL_KEY


def test_match_key_target_with_no_query_string_is_not_assumed():
    assert match_key("GET", "example.invalid", "/health") == "GET example.invalid /health"


# ------------------------------------------------------------------------- load_manifest

def test_load_manifest_round_trips_the_real_constructed_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        '{\n'
        '  "expires": "2099-01-01",\n'
        '  "responses": {\n'
        f'    "{REAL_KEY}": {{\n'
        '      "file": "responses/weather.json",\n'
        f'      "sha256": "{REAL_BODY_SHA256}"\n'
        '    }\n'
        '  }\n'
        '}\n',
        encoding="utf-8",
    )
    assert load_manifest(manifest_path) == {
        "expires": "2099-01-01",
        "responses": {
            REAL_KEY: {"file": "responses/weather.json", "sha256": REAL_BODY_SHA256},
        },
    }


# ------------------------------------------------------------------------- check_expiry

def test_check_expiry_on_the_expiry_date_itself_does_not_raise():
    check_expiry("2026-10-09", today=date(2026, 10, 9))


def test_check_expiry_one_day_past_raises_the_plan_exact_message():
    with pytest.raises(ReplaySetExpired) as exc_info:
        check_expiry("2026-10-09", today=date(2026, 10, 10))
    assert str(exc_info.value) == "replay set expired: re-record"


def test_check_expiry_far_future_does_not_raise():
    check_expiry("2099-01-01", today=date(2026, 10, 9))


# ------------------------------------------------------------------------- hash_matches

def test_hash_matches_the_real_sha256sum_digest_of_the_real_body():
    assert hash_matches(REAL_BODY, REAL_BODY_SHA256) is True


def test_hash_matches_rejects_a_flipped_final_hex_character():
    flipped = REAL_BODY_SHA256[:-1] + ("0" if REAL_BODY_SHA256[-1] != "0" else "1")
    assert hash_matches(REAL_BODY, flipped) is False


# ------------------------------------------------------------------------- parse_cert_enddate

def test_parse_cert_enddate_parses_the_real_openssl_line():
    assert parse_cert_enddate(REAL_ENDDATE_LINE) == datetime(2027, 10, 9, 6, 42, 51)


# ------------------------------------------------------------------------- check_leaf_freshness

def test_check_leaf_freshness_30_days_remaining_is_inside_the_last_month():
    enddate = datetime(2027, 1, 31)
    now = datetime(2027, 1, 1)
    with pytest.raises(LeafExpiringSoon):
        check_leaf_freshness(REAL_HOST, enddate, now)


def test_check_leaf_freshness_31_days_remaining_does_not_raise():
    enddate = datetime(2027, 2, 1)
    now = datetime(2027, 1, 1)
    check_leaf_freshness(REAL_HOST, enddate, now)


def test_check_leaf_freshness_already_past_enddate_raises():
    enddate = datetime(2026, 1, 1)
    now = datetime(2026, 6, 1)
    with pytest.raises(LeafExpiringSoon):
        check_leaf_freshness(REAL_HOST, enddate, now)


# ------------------------------------------------------------------------- decide

def _responses():
    return {REAL_KEY: {"file": "responses/weather.json", "sha256": REAL_BODY_SHA256}}


def test_decide_on_a_hit_returns_200_with_the_manifest_entry_and_a_hit_log_line():
    assert decide(_responses(), REAL_METHOD, REAL_HOST, REAL_TARGET) == Decision(
        status=200,
        log_line=f"HIT {REAL_KEY} sha256={REAL_BODY_SHA256}",
        file="responses/weather.json",
        sha256=REAL_BODY_SHA256,
    )


def test_decide_on_a_miss_returns_502_with_no_file_or_hash_and_the_plan_exact_log_line():
    miss_key = "GET example.invalid /unrecorded"
    assert decide(_responses(), "GET", "example.invalid", "/unrecorded") == Decision(
        status=502,
        log_line=f"MISS {miss_key}",
        file=None,
        sha256=None,
    )
