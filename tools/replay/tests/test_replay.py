"""Specifies replay.py's own respond(): every branch of the hit/miss decision, writing to a
plain BytesIO instead of a real socket and reading a real tmp_path response file. An autouse
fixture makes socket.create_connection raise, proving these calls never reach it.
"""
import socket
from io import BytesIO, StringIO

import pytest

from replay import respond

KEY = "GET example.invalid /weather?lat=1&lon=2"
BODY = b'{"temp_f": 72}'
SHA = "29391421140e7b282859469000378165c4c960a86077064929a089d71fd1061c"


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise AssertionError("respond() must never open a socket")
    monkeypatch.setattr(socket, "create_connection", _raise)


def _manifest():
    return {"responses": {KEY: {"file": "weather.json", "sha256": SHA}}}


def _call(manifest, set_dir, method="GET", host="example.invalid", target="/weather?lat=1&lon=2"):
    wfile = BytesIO()
    logf = StringIO()
    respond(manifest, set_dir, method, host, 443, target, {}, b"", wfile, logf)
    return wfile.getvalue(), logf.getvalue()


def test_respond_hit_writes_the_file_and_logs_hit(tmp_path):
    (tmp_path / "responses").mkdir()
    (tmp_path / "responses" / "weather.json").write_bytes(BODY)
    written, logged = _call(_manifest(), tmp_path)
    assert written == BODY
    assert f"HIT {KEY} sha256={SHA}" in logged


def test_respond_miss_writes_502_and_logs_miss(tmp_path):
    written, logged = _call(_manifest(), tmp_path, target="/unrecorded")
    assert written.startswith(b"HTTP/1.1 502")
    assert "MISS GET example.invalid /unrecorded" in logged


def test_respond_missing_response_file_is_a_miss(tmp_path):
    written, logged = _call(_manifest(), tmp_path)
    assert written.startswith(b"HTTP/1.1 502")
    assert "no response file" in logged


def test_respond_tampered_file_is_a_miss(tmp_path):
    (tmp_path / "responses").mkdir()
    (tmp_path / "responses" / "weather.json").write_bytes(b"tampered bytes, wrong hash")
    written, logged = _call(_manifest(), tmp_path)
    assert written.startswith(b"HTTP/1.1 502")
    assert "manifest hash mismatch" in logged
