"""Specifies proxy.py's pure parts: the match-key builder, manifest load, hash check,
the leaf-last-month check, the MISS/HIT decision, and the request/body/log-line transport
helpers over plain file-like objects (no socket).
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path

import proxy
from proxy import (
    check_leaf_freshness,
    decide,
    hash_matches,
    known_hosts,
    leaf_paths,
    load_manifest,
    log_line,
    manifest_hash,
    match_key,
    parse_cert_enddate,
    read_body,
    read_request,
    stale_leaves,
)

REAL_METHOD = "GET"
REAL_HOST = "example.invalid"
REAL_TARGET = "/weather?lat=1&lon=2"
REAL_KEY = "GET example.invalid /weather?lat=1&lon=2"
REAL_BODY = b'{"temp_f": 72}'
REAL_BODY_SHA256 = "29391421140e7b282859469000378165c4c960a86077064929a089d71fd1061c"
REAL_ENDDATE_LINE = "notAfter=Oct  9 06:42:51 2027 GMT"


def _responses():
    return {REAL_KEY: {"file": "responses/weather.json", "sha256": REAL_BODY_SHA256}}


def test_match_key_builds_method_host_target():
    assert match_key(REAL_METHOD, REAL_HOST, REAL_TARGET) == REAL_KEY


def test_load_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"responses": {}}', encoding="utf-8")
    assert load_manifest(manifest_path) == {"responses": {}}


def test_hash_matches_the_real_sha256sum_digest():
    assert hash_matches(REAL_BODY, REAL_BODY_SHA256) is True


def test_hash_matches_rejects_a_flipped_final_hex_character():
    flipped = REAL_BODY_SHA256[:-1] + ("0" if REAL_BODY_SHA256[-1] != "0" else "1")
    assert hash_matches(REAL_BODY, flipped) is False


def test_parse_cert_enddate_parses_the_real_openssl_line():
    assert parse_cert_enddate(REAL_ENDDATE_LINE) == datetime(2027, 10, 9, 6, 42, 51)


def test_check_leaf_freshness_30_days_remaining_is_inside_the_last_month():
    assert check_leaf_freshness(REAL_HOST, datetime(2027, 1, 31), datetime(2027, 1, 1)) == \
        f"{REAL_HOST} (expires 2027-01-31)"


def test_check_leaf_freshness_31_days_remaining_is_none():
    assert check_leaf_freshness(REAL_HOST, datetime(2027, 2, 1), datetime(2027, 1, 1)) is None


def test_check_leaf_freshness_already_past_enddate_is_a_reason():
    assert check_leaf_freshness(REAL_HOST, datetime(2026, 1, 1), datetime(2026, 6, 1)) is not None


def test_decide_on_a_hit_returns_the_manifest_entry():
    assert decide(_responses(), REAL_METHOD, REAL_HOST, REAL_TARGET) == {
        "file": "responses/weather.json", "sha256": REAL_BODY_SHA256,
    }


def test_decide_on_a_miss_returns_none():
    assert decide(_responses(), "GET", "example.invalid", "/unrecorded") is None


def test_known_hosts_from_the_manifests_own_response_keys():
    assert known_hosts({"responses": _responses()}) == {"example.invalid"}


def test_leaf_paths():
    assert leaf_paths(Path("/ca"), "example.invalid") == (
        Path("/ca/leaves/example.invalid.crt"), Path("/ca/leaves/example.invalid.key"))


def test_manifest_hash_is_the_real_sha256sum_of_the_file(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(b"abc")
    assert manifest_hash(manifest_path) == \
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_stale_leaves_no_crt_is_reported_as_no_leaf(tmp_path):
    ca_dir = tmp_path / "ca"
    cert, _key = leaf_paths(ca_dir, REAL_HOST)
    assert stale_leaves(ca_dir, {REAL_HOST}) == [f"{REAL_HOST} (no leaf at {cert})"]


def test_stale_leaves_crt_without_key_is_reported_as_no_leaf(tmp_path):
    ca_dir = tmp_path / "ca"
    cert, key = leaf_paths(ca_dir, REAL_HOST)
    cert.parent.mkdir(parents=True)
    cert.write_bytes(b"cert")
    assert not key.is_file()
    assert stale_leaves(ca_dir, {REAL_HOST}) == [f"{REAL_HOST} (no leaf at {cert})"]


def test_stale_leaves_fresh_leaf_is_empty(tmp_path, monkeypatch):
    ca_dir = tmp_path / "ca"
    cert, key = leaf_paths(ca_dir, REAL_HOST)
    cert.parent.mkdir(parents=True)
    cert.write_bytes(b"cert")
    key.write_bytes(b"key")
    monkeypatch.setattr(proxy, "leaf_expiry", lambda _cert: datetime(2027, 6, 1))
    assert stale_leaves(ca_dir, {REAL_HOST}, now=datetime(2027, 1, 1)) == []


def test_stale_leaves_leaf_inside_its_last_month_is_reported(tmp_path, monkeypatch):
    ca_dir = tmp_path / "ca"
    cert, key = leaf_paths(ca_dir, REAL_HOST)
    cert.parent.mkdir(parents=True)
    cert.write_bytes(b"cert")
    key.write_bytes(b"key")
    monkeypatch.setattr(proxy, "leaf_expiry", lambda _cert: datetime(2027, 1, 20))
    assert stale_leaves(ca_dir, {REAL_HOST}, now=datetime(2027, 1, 1)) == \
        [f"{REAL_HOST} (expires 2027-01-20)"]


def test_read_request_connect_line():
    rfile = BytesIO(b"CONNECT example.invalid:443 HTTP/1.1\r\nHost: example.invalid:443\r\n\r\n")
    method, target, headers = read_request(rfile)
    assert (method, target) == ("CONNECT", "example.invalid:443")
    assert headers["Host"] == "example.invalid:443"


def test_read_request_inner_get_with_query():
    rfile = BytesIO(f"GET {REAL_TARGET} HTTP/1.1\r\nHost: {REAL_HOST}\r\n\r\n".encode())
    method, target, _headers = read_request(rfile)
    assert (method, target) == ("GET", REAL_TARGET)


def test_read_request_eof_is_none():
    assert read_request(BytesIO(b"")) is None


def test_read_body_present():
    rfile = BytesIO(b'{"a":1}')
    headers = {"Content-Length": "7"}
    assert read_body(rfile, headers) == b'{"a":1}'


def test_read_body_absent_is_empty():
    assert read_body(BytesIO(b"unread"), {}) == b""


def test_log_line_appends_a_timestamped_line(tmp_path):
    logf = (tmp_path / "access.log").open("a", encoding="utf-8")
    log_line(logf, "HIT a b c")
    logf.close()
    text = (tmp_path / "access.log").read_text(encoding="utf-8")
    assert text.endswith("HIT a b c\n")
    assert text.split(" ", 1)[0].count("-") == 2  # an ISO date prefix
