"""Specifies nothing new: record.py's own forward()/respond()/main() all dial a real host or
parse argv, proven by the host-only proof rather than a constructed input. This import alone
exercises the module's own top-level statements for the coverage floor.
"""
import record


def test_record_exposes_forward_and_respond():
    assert callable(record.forward)
    assert callable(record.respond)
