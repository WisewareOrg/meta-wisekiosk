"""TST002: the render-advancing check, judged by `verdicts.render`."""

import time

from verdicts.applied import verdict as applied_verdict
from verdicts.render import verdict

_APPLIED_WAIT_SECONDS = 90
_POLL_SECONDS = 2

# docs/testing.md section "Running it" has the why for this default crop.
_CROP = "560x300+220+20"
_RENDER_PROBE = (
    'if ! command -v import > /dev/null 2>&1; then echo "cap import=0"; exit 0; fi\n'
    "F=/tmp/render-check.$$\n"
    "grab() {\n"
    "    n=$1\n"
    '    DISPLAY=:0 import -window root -crop "%s" +repage "$F.$n.png" > /dev/null 2>"$F.$n.err"\n'
    "    rc=$?\n"
    '    if [ -f "$F.$n.png" ]; then\n'
    '        b=$(wc -c < "$F.$n.png")\n'
    '        m=$(md5sum < "$F.$n.png" | cut -d\' \' -f1)\n'
    "    else\n"
    "        b=0\n"
    "        m=none\n"
    "    fi\n"
    '    err=$(tr \'\\n\' \' \' < "$F.$n.err" 2>/dev/null | tr -s \' \' \'_\')\n'
    '    echo "frame $n rc=$rc bytes=$b md5=$m err=${err:-none}"\n'
    "}\n"
    "grab 1\n"
    "sleep 3\n"
    "grab 2\n"
    'if command -v identify > /dev/null 2>&1 && [ -f "$F.2.png" ]; then\n'
    "    identify -format 'blank min=%%[fx:minima*255] max=%%[fx:maxima*255] "
    "mean=%%[fx:mean*255]\\n' \"$F.2.png\" 2>/dev/null\n"
    "fi\n"
    'rm -f "$F.1.png" "$F.2.png" "$F.1.err" "$F.2.err"\n'
) % _CROP


def test_render_advancing(target, probe):
    """TST002: two screenshots 3 s apart differ, so the render repainted within the interval.

    Waits for the probe to report state=applied first. Measured on bench: from a
    `kiosk.service` restart, the probe reports nothing for ~13s, `error:not-app` for the next
    ~8s, then `applied` around 20-28s -- capturing before that point measures a loading screen,
    not rendering, which is what made this check depend on what ran immediately before it in
    the same session (nothing in the old, per-stage pipeline needed this wait, since nothing
    there ran a render capture right after a browser restart).

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.
        probe: deploys `probe.js` and restarts the browser; yields a reader for its latest
            sample.
    """
    deadline = time.monotonic() + _APPLIED_WAIT_SECONDS
    samples = []
    while True:
        samples.append(probe())
        applied_outcome, applied_reason = applied_verdict(samples)
        if applied_outcome == "applied" or time.monotonic() >= deadline:
            break
        time.sleep(_POLL_SECONDS)
    if applied_outcome != "applied":
        raise RuntimeError(f"page did not apply before the render check: {applied_outcome}:{applied_reason}")

    driver = target.get_driver("SSHDriver")
    stdout, _stderr, _rc = driver.run(_RENDER_PROBE)
    outcome, reason = verdict(stdout)
    if outcome == "advancing":
        return
    if outcome == "frozen":
        raise AssertionError(reason)
    raise RuntimeError(f"{outcome}: {reason}")
