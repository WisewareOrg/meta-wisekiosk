from framework.base import WiseKioskCase

from .verdict import verdict as render_verdict

# The render check's default crop, ported from tools/kiosk-render-check.sh --
# docs/testing.md § "The render and applied cases" has the why.
_RENDER_CROP = "560x300+220+20"
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
) % _RENDER_CROP


class KioskRenderTest(WiseKioskCase):

    def test_render_advancing(self):
        _status, output = self.target.run(_RENDER_PROBE)
        outcome, reason = render_verdict(output.splitlines())
        if outcome == "advancing":
            return
        if outcome == "frozen":
            self.fail(reason)
        raise RuntimeError(reason)
