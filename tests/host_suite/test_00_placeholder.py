"""No host-side suite exists yet (meta-wisekiosk#226). `bench test` refuses an absent
`tests/host_suite/` directory as its own failure, so this placeholder keeps the run on the
candidate's own failure path until #226 fills the suite in.
"""


def test_placeholder():
    pass
