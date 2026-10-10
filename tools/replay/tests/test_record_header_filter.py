"""Specifies record.py's own pure header filter."""
import pytest

from record import _skip_response_header


@pytest.mark.parametrize(
    ("name", "header", "want"),
    [
        ("CF-RAY is identity, dropped", "CF-RAY", True),
        ("any cf-* header is dropped, case-insensitively", "cf-cache-status", True),
        ("a hop-by-hop header this tool recomputes is dropped", "Content-Length", True),
        ("an ordinary header is kept", "Content-Type", False),
        ("a header merely containing cf is not cf-*", "X-CF-Forwarded", False),
    ],
)
def test_skip_response_header(name, header, want):
    assert _skip_response_header(header) == want, name
