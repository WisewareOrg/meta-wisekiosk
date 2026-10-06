#!/usr/bin/env python3
"""Smoothness verdict: a WPE candidate's framepace records against an X baseline's.

    kiosk-framepace-verdict.py --baseline F [F ...] --candidate F [F ...]

Each file is one kiosk-smoothness-check.sh record, analyzed by kiosk-framepace.py.
Per metric, the candidate's worst run is compared with the baseline's worst run,
worse direction only: presented_fps and pct_under_50 regress when the candidate's
minimum is below the baseline's minimum, stall_rate when the candidate's maximum
is above the baseline's maximum. A metric whose candidate worst beats the
baseline's best is reported as an improvement; that never changes the exit code.

Exit 0 no regression, 1 a regression (each named), 2 could not tell: a record is
not rc 0, either group has fewer than 3 records, a baseline record is not engine
X or a candidate record not engine WPE, or the records do not share one host_role.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

MIN_RECORDS = 3
# metric -> True when higher is better
METRICS = {"presented_fps": True, "pct_under_50": True, "stall_rate": False}


def _load_analyzer():
    spec = importlib.util.spec_from_file_location(
        "kiosk_framepace", Path(__file__).resolve().parent / "kiosk-framepace.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fp = _load_analyzer()


def _group(name, records, engine, reasons):
    """(results, host_roles) for one group, appending why it cannot be used."""
    results, roles = [], set()
    if len(records) < MIN_RECORDS:
        reasons.append(f"{name} has {len(records)} records, fewer than {MIN_RECORDS}")
    for i, lines in enumerate(records, 1):
        result = fp.analyze(lines)
        roles.add(fp.parse(lines)[1].get("host_role", ""))
        if result["rc"] != 0:
            reasons.append(f"{name} record {i} is rc {result['rc']}: " + "; ".join(result["reasons"]))
        elif result["engine"] != engine:
            reasons.append(f"{name} record {i} is engine {result['engine']}, not {engine}")
        results.append(result)
    return results, roles


def framepace_verdict(baseline_records, candidate_records):
    reasons = []
    base, base_roles = _group("baseline", baseline_records, "X", reasons)
    cand, cand_roles = _group("candidate", candidate_records, "WPE", reasons)
    if len(base_roles | cand_roles) > 1:
        reasons.append("records span host roles " + ", ".join(sorted(base_roles | cand_roles)))
    if reasons:
        return {"rc": 2, "reasons": reasons}

    ranges = {group: {m: (min(r[m] for r in results), max(r[m] for r in results))
                      for m in METRICS}
              for group, results in (("baseline", base), ("candidate", cand))}
    improvements = []
    for metric, higher_better in METRICS.items():
        (b_min, b_max), (c_min, c_max) = ranges["baseline"][metric], ranges["candidate"][metric]
        if higher_better:
            regressed, improved = c_min < b_min, c_min > b_max
            worst, baseline_worst = c_min, b_min
        else:
            regressed, improved = c_max > b_max, c_max < b_min
            worst, baseline_worst = c_max, b_max
        if regressed:
            reasons.append(f"{metric}: candidate worst {worst:.3f} is worse than "
                           f"baseline worst {baseline_worst:.3f}")
        if improved:
            improvements.append(metric)
    return {"rc": 1 if reasons else 0, "reasons": reasons, "ranges": ranges,
            "improvements": improvements}


def main(argv):
    parser = argparse.ArgumentParser(prog="kiosk-framepace-verdict.py")
    parser.add_argument("--baseline", nargs="+", required=True)
    parser.add_argument("--candidate", nargs="+", required=True)
    args = parser.parse_args(argv[1:])
    read = lambda paths: [Path(p).read_text(encoding="utf-8").splitlines() for p in paths]
    result = framepace_verdict(read(args.baseline), read(args.candidate))
    for group, metrics in result.get("ranges", {}).items():
        for metric, (lo, hi) in metrics.items():
            print(f"{group} {metric} min={lo:.3f} max={hi:.3f}")
    for metric in result.get("improvements", []):
        print(f"improvement: {metric}")
    prefix = "could not tell: " if result["rc"] == 2 else "regression: "
    for reason in result["reasons"]:
        print(prefix + reason)
    return result["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
