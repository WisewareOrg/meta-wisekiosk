#!/usr/bin/env python3
"""
Report each run's own webkitgtk3 .ninja_log stats for the real long-pole
compile work: single-output .o edges under
Source/{WebCore,JavaScriptCore,WebKit,WTF,bmalloc,WebKitLegacy}/, excluding
WebDriver/, po/*.gmo and MiniBrowser -- WebKitWebDriver links only against
WTF and system libraries, not libwebkit2gtk, so matching by raw output set
or by edge index makes it (and other no-dependency stragglers) a false
"straggler" that collapses a comparison to a few seconds.

Prints ONE block per run, each its own table -- no run's numbers share a
table with another's (R3). Ratios between runs are for the caller to state
in prose from these per-run numbers, not something this script tables.

Usage: ninja-log-compare.py <name>=<path.ninja_log> [<name>=<path.ninja_log> ...]
  Decompress the committed .xz inputs first, e.g.:
    xz -dc ninja_log-20261004023340.xz > /tmp/current.ninja_log
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


def span_s(obj_edges_dict, edges, names):
    rows = [e for e in edges if len(e["outputs"]) == 1 and e["outputs"][0] in names]
    if not rows:
        return None
    return (max(r["end_ms"] for r in rows) - min(r["start_ms"] for r in rows)) / 1000.0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    runs = dict(a.split("=", 1) for a in sys.argv[1:])
    data = {}
    for name, path in runs.items():
        edges = load_edges(path)
        data[name] = (edges, core_obj_edges(edges))

    for name, (edges, obj) in data.items():
        edge_span = span_s(obj, edges, set(obj))
        mean_ms = sum(obj.values()) / len(obj) if obj else 0
        print(f"=== {name} ===")
        print(f"total ninja edges        : {len(edges)}")
        print(f"core .o edges (this run)  : {len(obj)}")
        print(f"mean core .o duration (ms): {mean_ms:.0f}")
        print(f"total span over core .o edges (s): {edge_span:.1f}" if edge_span else "total span: n/a")
        for other, (_oe, oobj) in data.items():
            if other == name:
                continue
            shared = len(set(obj) & set(oobj))
            print(f"core .o edges shared with {other}: {shared} of {len(obj)}")
        print()


if __name__ == "__main__":
    main()
