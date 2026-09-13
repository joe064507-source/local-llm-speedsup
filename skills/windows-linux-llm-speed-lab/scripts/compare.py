"""Compare matched benchmark reports; no inference, external writes or networking."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


def measured(report):
    if report.get("version") != 1 or report.get("preview_only") or not report.get("complete"):
        raise ValueError("Only completed live reports can be compared")
    for field in ("model", "fixture_sha256"):
        if not isinstance(report.get(field), str) or not report[field]:
            raise ValueError("Missing comparison identity: " + field)
    for field, minimum, maximum in (("warmups", 0, 10), ("repeats", 1, 20)):
        if type(report.get(field)) is not int or not minimum <= report[field] <= maximum:
            raise ValueError("Invalid declared trial count: " + field)
    rows = report.get("rows", [])
    if not rows or any(not row.get("valid") for row in rows):
        raise ValueError("A failed warm-up or measured trial must be reported, not dropped")
    stages = {"warmup": {}, "warm": {}}
    for row in rows:
        stage = row.get("stage")
        if stage not in stages:
            raise ValueError("Unknown trial stage")
        seconds = row.get("seconds")
        if type(seconds) not in (float, int) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Invalid complete-request latency")
        key = (row["case"], row["trial"])
        count = report["warmups" if stage == "warmup" else "repeats"]
        if type(row["trial"]) is not int or not 1 <= row["trial"] <= count:
            raise ValueError("Trial index outside declared schedule")
        if not isinstance(row.get("request_sha256"), str) or not row["request_sha256"]:
            raise ValueError("Missing request fingerprint")
        if key in stages[stage]:
            raise ValueError("Duplicate scheduled trial")
        stages[stage][key] = row
    selected = stages["warm"]
    if not selected:
        raise ValueError("No measured trials")
    cases = {key[0] for trials in stages.values() for key in trials}
    for stage, field in (("warmup", "warmups"), ("warm", "repeats")):
        expected = {(case, trial) for case in cases for trial in range(1, report[field] + 1)}
        if stages[stage].keys() != expected:
            raise ValueError("Missing scheduled trials: " + stage)
    return selected


def compare(pairs):
    by_case = {}
    isolated = True
    enough = len(pairs) >= 2
    identities_recorded = True
    seen_trials = set()
    for off, on in pairs:
        for field in ("model", "fixture_sha256", "identity_sha256", "warmups", "repeats", "seed"):
            if off.get(field) != on.get(field):
                raise ValueError("Mismatched comparison field: " + field)
        identities_recorded = identities_recorded and bool(off.get("identity_sha256"))
        before, after = measured(off), measured(on)
        for report in (off, on):
            # Labels and file names do not make copied trials new measurements.
            fingerprint = hashlib.sha256(json.dumps(report["rows"], sort_keys=True,
                                                    separators=(",", ":")).encode()).digest()
            if fingerprint in seen_trials:
                raise ValueError("Reused trial evidence; each state/pair needs a fresh run")
            seen_trials.add(fingerprint)
        if before.keys() != after.keys():
            raise ValueError("Mismatched cases or trial indices")
        enough = enough and off["repeats"] >= 3
        for key in before:
            a, b = before[key], after[key]
            if a.get("request_sha256") != b.get("request_sha256") or a.get("seed") != b.get("seed"):
                raise ValueError("Mismatched request payloads")
            isolated = isolated and a.get("isolation") == b.get("isolation") == "counter_verified"
        for case in sorted({key[0] for key in before}):
            a = statistics.median(row["seconds"] for key, row in before.items() if key[0] == case)
            b = statistics.median(row["seconds"] for key, row in after.items() if key[0] == case)
            by_case.setdefault(case, []).append({"before_median_s": a, "after_median_s": b,
                                                "time_reduction_percent": 100 * (1 - b / a)})
    cases = {case: {"pairs": values, "improved_in_every_pair": all(v["time_reduction_percent"] > 0 for v in values)}
             for case, values in by_case.items()}
    enough = enough and all(len(values) >= 2 for values in by_case.values())
    return {"cases": cases, "two_pairs_three_repeats_minimum": enough,
            "declared_hardware_model_identity_recorded": identities_recorded,
            "measured_trial_overlap_counter_verified": isolated,
            "scope": "Complete warm model requests for matched fixture cases; not raw decode speed.",
            "quality_caveat": "Declared correctness screens passed; broader reasoning/tool/vision quality is not established.",
            "recommendation": "Inspect all cases, output lengths, cold/novel workloads and resource/quality checks before retaining a change."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", action="append", nargs=2, required=True, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()
    try:
        reports = [(json.loads(Path(a).read_text()), json.loads(Path(b).read_text())) for a, b in args.pair]
        print(json.dumps(compare(reports), indent=2))
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"comparison_rejected": type(error).__name__, "detail": "Reports must be complete, valid and matched; do not omit failed trials."}))
        raise SystemExit(2)
