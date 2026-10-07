#!/usr/bin/env python3
"""Self-test for tools/device-role.py's identity-fence reader.

    device-role-test.py        -- every case

`resolve_role(fence_text, address)` is the importable seam: it scans a ```identity fence the same
way tools/scrub-identity.py does, finds the row `<role>.address = <address>`, and returns that
role's `(role, hostname)` -- but only for role in {prod, bench}; any other role's address raises
"no role has address X", the same as an address matching no row at all. Tested by behaviour only
-- never by asserting how the fence is parsed. Every fixture here is invented -- role names,
addresses and hostnames fabricated for the case -- never a line of the real, gitignored
local/device-identity.md, which this test never reads.
"""
import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


device_role = load("device-role")

PASS, FAIL = [], []


def case(name, got, want):
    (PASS if got == want else FAIL).append(name)
    if got != want:
        print(f"FAIL  {name}\n        want {want!r}\n        got  {got!r}")


# RFC 5737 TEST-NET-3 addresses -- never a real host's, and no RFC1918 shape
# either, so this fixture cannot be mistaken for a real device map. The
# key = value row above the fence is shaped exactly like a real row, to prove
# the reader is scoped to the fence and does not scan surrounding prose. A
# well-formed "router" row inside the fence proves the prod/bench restriction
# itself -- its row is real and parseable, but router is neither candidate.
FENCE = """A decoy row outside the fence, shaped like a real one:
prod.address = 203.0.113.250

```identity
prod.address = 203.0.113.9
prod.hostname = prod-host
bench.address = 203.0.113.10
bench.hostname = bench-host
router.address = 203.0.113.11
router.hostname = router-host
```

More prose below the fence.
"""


def resolve_role_cases():
    case("resolve_role: finds prod by its own address",
         device_role.resolve_role(FENCE, "203.0.113.9"), ("prod", "prod-host"))
    case("resolve_role: finds bench by its own address",
         device_role.resolve_role(FENCE, "203.0.113.10"), ("bench", "bench-host"))

    try:
        device_role.resolve_role(FENCE, "203.0.113.11")
        raised = None
    except ValueError as exc:
        raised = exc
    case("resolve_role: a well-formed row for a role that is neither prod nor bench"
         " still raises -- role is not the candidate, not whether a row exists",
         raised is not None, True)
    case("resolve_role: that refusal names the address", "203.0.113.11" in str(raised), True)

    try:
        device_role.resolve_role(FENCE, "203.0.113.250")
        raised = None
    except ValueError as exc:
        raised = exc
    case("resolve_role: a row shaped like a real one but outside the fence is not scanned"
         " (its address resolves to no role)", raised is not None, True)
    case("resolve_role: the refusal names the address", "203.0.113.250" in str(raised), True)

    try:
        device_role.resolve_role(FENCE, "203.0.113.251")
        raised = None
    except ValueError as exc:
        raised = exc
    case("resolve_role: an address naming no role at all raises", raised is not None, True)


def main() -> int:
    resolve_role_cases()
    print(f"\npass={len(PASS)} fail={len(FAIL)} skip=0")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
