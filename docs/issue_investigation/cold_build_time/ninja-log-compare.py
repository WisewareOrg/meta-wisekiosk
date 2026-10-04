#!/usr/bin/env python3
"""
Compare webkitgtk3 do_compile .ninja_log files, matched by output FILENAME
(not edge index -- a -j2 vs -j6 schedule legitimately reorders independent
work). Restricted to the real long-pole compile work: single-output .o edges
under Source/{WebCore,JavaScriptCore,WebKit,WTF,bmalloc,WebKitLegacy}/,
excluding WebDriver/, po/*.gmo and MiniBrowser -- WebKitWebDriver links only
against WTF + system libs, not libwebkit2gtk, so it has no true dependency on
the long compile tail and otherwise dominates match-set edge cases as an
outlier straggler.

Usage: ninja-log-compare.py <current.ninja_log> <name>=<path.ninja_log> ...
"""
import sys
from collections import defaultdict

CORE_DIRS = ("Source/WebCore/", "Source/JavaScriptCore/", "Source/WebKit/",
             "Source/WTF/", "Source/bmalloc/", "Source/WebKitLegacy/")


def norm_output(path):
    marker = "/build/"
    idx = path.rfind(marker)
    return path[idx + len(marker):] if idx != -1 else path


def load_edges(path):
    groups = defaultdict(list)
    with open(path, errors="replace") as f:
        f.readline()
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 5:
                continue
            start_ms, end_ms, _mtime_ns, out, h = parts
            groups[(int(start_ms), int(end_ms), h)].append(norm_output(out))
    edges = []
    for (start_ms, end_ms, _h), outs in groups.items():
        edges.append({"start_ms": start_ms, "end_ms": end_ms,
                       "dur_ms": end_ms - start_ms, "outputs": outs})
    edges.sort(key=lambda e: e["end_ms"])
    return edges


def core_obj_edges(edges):
    """{output: dur_ms} for single-output .o edges under the core dirs."""
    out = {}
    for e in edges:
        if len(e["outputs"]) != 1:
            continue
        o = e["outputs"][0]
        if not o.endswith(".o"):
            continue
        if not any(o.startswith(d) or ("/" + d) in o for d in CORE_DIRS):
            continue
        out[o] = e["dur_ms"]
    return out


def span(edges, names):
    """Wall-clock span (s) from first start to last end among these outputs."""
    rows = [e for e in edges if len(e["outputs"]) == 1 and e["outputs"][0] in names]
    if not rows:
        return None
    return (max(r["end_ms"] for r in rows) - min(r["start_ms"] for r in rows)) / 1000.0


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cur_path = sys.argv[1]
    priors = dict(a.split("=", 1) for a in sys.argv[2:])

    current = load_edges(cur_path)
    cur_obj = core_obj_edges(current)
    cur_names = set(cur_obj)
    cur_span = span(current, cur_names)

    print(f"current: {len(current)} edges, {len(cur_obj)} core .o edges, "
          f"span {cur_span:.1f}s")

    for name, path in priors.items():
        edges = load_edges(path)
        prior_obj = core_obj_edges(edges)
        common = cur_names & set(prior_obj)
        prior_span_matched = span(edges, common)
        cur_span_matched = span(current, common)
        cur_mean = sum(cur_obj[o] for o in common) / len(common)
        prior_mean = sum(prior_obj[o] for o in common) / len(common)
        print(f"\n--- vs {name} ({len(prior_obj)} core .o edges, "
              f"{len(common)} matched) ---")
        print(f"  per-unit mean: current={cur_mean:.0f}ms prior={prior_mean:.0f}ms "
              f"(current/prior={cur_mean / prior_mean:.2f}x)")
        print(f"  throughput span over matched set: current={cur_span_matched:.1f}s "
              f"prior={prior_span_matched:.1f}s "
              f"(prior/current={prior_span_matched / cur_span_matched:.2f}x)")


if __name__ == "__main__":
    main()
