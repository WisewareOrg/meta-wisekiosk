"""No host-side suite exists yet (meta-wisekiosk#226, "The host suite"). `bench test` maps both an
absent `tests/host_suite/` directory (pytest exit 4, no such path) and a present-but-empty one
(pytest exit 5, nothing collected) to the runner's own `BenchFailure`, not the candidate's -- a
hook or test failure stays separate from an infrastructure gap. This placeholder keeps the suite
on the candidate-failure path, with one real passing test, until meta-wisekiosk#226 fills it in.
"""


def test_placeholder():
    """Pass unconditionally -- keeps this directory non-empty until meta-wisekiosk#226 lands."""
