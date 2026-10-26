#!/usr/bin/env python3
"""Recompute W1 SSH-clock probe evidence; standard library only, no network.

Default input is the accompanying sanitized, per-run evidence CSVs. To extract
it afresh, supply --run-root and --registry referring to local accepted W1 runs.
Source run-health files are opened read-only; outputs must be a different path.
"""

import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
import re
import statistics
import sys


ROLES = ("core", "ran", "traffic")
REMOTE_ROLES = ("ran", "traffic")
FIELDS = (
    "run", "host_role", "sample_index", "timestamp_utc", "available",
    "probe_present", "offset_ms", "raw_offset_ms", "offset_uncertainty_ms",
    "probe_latency_ms", "local_interval_ms", "record_clock_skew_ms",
    "formula_checked", "formula_consistent", "validity", "flags",
)
NUMERIC = (
    "offset_ms", "raw_offset_ms", "offset_uncertainty_ms", "probe_latency_ms",
    "local_interval_ms", "record_clock_skew_ms",
)


def finite(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def timestamp(value):
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.timestamp() if result.tzinfo else None
    except (AttributeError, ValueError, OverflowError):
        return None


def producer(remote, before, after):
    """Exact arithmetic in frozen scripts/run_health_monitor.sh."""
    interval = after - before
    latency = max(0, interval)
    raw = remote - (before + after) / 2
    uncertainty = latency / 2
    offset = remote - before if remote < before else (
        remote - after if remote > after else 0
    )
    return raw, uncertainty, offset, latency, interval


def quantile(values, probability):
    """Linear interpolation at (n-1)*p; empty groups have null results."""
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def distribution(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return {
        "n": len(values),
        "median": statistics.median(values) if values else None,
        "p95": quantile(values, 0.95),
        "max": max(values) if values else None,
    }


def extract(run_root, registry_path):
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    accepted = registry["accepted"]
    if len(accepted) != 7 or len(set(accepted)) != 7:
        raise ValueError("Expected exactly seven unique accepted W1 runs")
    slot_ids = {}
    for run_id in accepted:
        match = re.search(r"_D(0[1-7])_", run_id)
        if not match or match[1] in slot_ids:
            raise ValueError("Accepted runs do not map uniquely to D01-D07")
        slot_ids[match[1]] = run_id
    for slot, run_id in sorted(slot_ids.items()):
        print("Reading W1-D" + slot, file=sys.stderr)
        with (run_root / run_id / "metrics" / "run-health.jsonl").open(
            encoding="utf-8"
        ) as stream:
            for sample_index, line in enumerate(stream, 1):
                record = json.loads(line)
                probes = record.get("clock_probes") or []
                for role in ROLES:
                    matches = [p for p in probes if p.get("host_role") == role]
                    if len(matches) > 1:
                        raise ValueError("Duplicate host_role in a health record")
                    probe = matches[0] if matches else {}
                    row = dict.fromkeys(FIELDS, None)
                    row.update(
                        run="W1-D" + slot, host_role=role,
                        sample_index=sample_index,
                        timestamp_utc=record.get("timestamp", ""),
                        available=probe.get("available") is True,
                        probe_present=bool(matches), formula_checked=False,
                        formula_consistent=False,
                        record_clock_skew_ms=finite(record.get("clock_skew_ms")),
                    )
                    for field in NUMERIC:
                        if field not in ("local_interval_ms", "record_clock_skew_ms"):
                            row[field] = finite(probe.get(field))
                    flags = []
                    if timestamp(row["timestamp_utc"]) is None:
                        flags.append("invalid_health_timestamp")
                    if role == "core":
                        row["validity"] = "reference_only"
                    elif not matches:
                        row["validity"] = "missing_probe"
                    elif not row["available"]:
                        row["validity"] = "unavailable"
                    else:
                        epochs = [finite(probe.get(k)) for k in (
                            "remote_epoch_ms", "local_before_epoch_ms",
                            "local_after_epoch_ms",
                        )]
                        present = [row[k] for k in (
                            "raw_offset_ms", "offset_uncertainty_ms",
                            "offset_ms", "probe_latency_ms",
                        )]
                        if any(v is None for v in epochs + present):
                            row["validity"] = "invalid_missing_or_nonfinite_numeric"
                        else:
                            expected = producer(*epochs)
                            row["local_interval_ms"] = expected[4]
                            row["formula_checked"] = True
                            row["formula_consistent"] = all(
                                abs(actual - target) <= 0.001
                                for actual, target in zip(present, expected[:4])
                            )
                            if expected[4] < 0:
                                row["validity"] = "invalid_reversed_local_interval"
                            elif not row["formula_consistent"]:
                                row["validity"] = "invalid_producer_formula_mismatch"
                            elif row["offset_uncertainty_ms"] < 0:
                                row["validity"] = "invalid_negative_uncertainty"
                            else:
                                row["validity"] = "valid_probe_interval"
                            if expected[4] < 0:
                                flags.append("reversed_local_interval")
                            if not row["formula_consistent"]:
                                flags.append("producer_formula_mismatch")
                    if row["raw_offset_ms"] is not None and abs(row["raw_offset_ms"]) > 1000:
                        flags.append("abs_midpoint_offset_gt_1000ms")
                    if row["offset_uncertainty_ms"] is not None and row["offset_uncertainty_ms"] > 1000:
                        flags.append("half_interval_gt_1000ms")
                    row["flags"] = ";".join(flags)
                    yield row


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_evidence(path):
    if path.is_dir():
        paths = sorted(path.glob("clock_evidence_W1-D??.csv"))
        if len(paths) != 7:
            raise ValueError("Expected seven per-run clock evidence CSVs")
        for item in paths:
            yield from read_evidence(item)
        return
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames) != FIELDS:
            raise ValueError("Unexpected clock evidence schema")
        for row in reader:
            for key in NUMERIC:
                row[key] = finite(row[key])
            for key in ("available", "probe_present", "formula_checked", "formula_consistent"):
                if row[key] not in ("True", "False"):
                    raise ValueError("Expected explicit boolean in " + key)
                row[key] = row[key] == "True"
            row["sample_index"] = int(row["sample_index"])
            yield row


def summarize_group(rows, run, role):
    groups = {}
    for row in rows:
        groups[row["validity"]] = groups.get(row["validity"], 0) + 1
    health_samples = sorted(set(
        (r["run"], r["sample_index"], r["timestamp_utc"]) for r in rows
    ))
    by_run = {}
    for run_id, _, ts in health_samples:
        by_run.setdefault(run_id, []).append(timestamp(ts))
    gaps, span, reversals, duplicates, invalid_timestamps = [], 0, 0, 0, 0
    for points in by_run.values():
        invalid_timestamps += sum(t is None for t in points)
        points = [t for t in points if t is not None]
        if len(points) > 1:
            span += max(points) - min(points)
            differences = [b - a for a, b in zip(points, points[1:])]
            reversals += sum(t < 0 for t in differences)
            duplicates += sum(t == 0 for t in differences)
            gaps.extend(t for t in differences if t >= 0)
    def values(key, absolute=False, valid_only=False):
        selected = rows if not valid_only else [
            r for r in rows if r["validity"] == "valid_probe_interval"
        ]
        return [abs(r[key]) if absolute else r[key] for r in selected if r[key] is not None]
    bounds_all_finite = [
        abs(r["raw_offset_ms"]) + r["offset_uncertainty_ms"] for r in rows
        if r["raw_offset_ms"] is not None and r["offset_uncertainty_ms"] is not None
    ]
    bounds_valid = [
        abs(r["raw_offset_ms"]) + r["offset_uncertainty_ms"] for r in rows
        if r["validity"] == "valid_probe_interval"
    ]
    metrics = {
        "abs_midpoint_offset_ms_all_finite": distribution(values("raw_offset_ms", True)),
        "half_interval_uncertainty_ms_all_finite": distribution(values("offset_uncertainty_ms")),
        "abs_interval_residual_ms_all_finite": distribution(values("offset_ms", True)),
        "abs_raw_plus_uncertainty_ms_all_finite": distribution(bounds_all_finite),
        "abs_raw_plus_uncertainty_ms_valid_intervals": distribution(bounds_valid),
        "probe_latency_ms_all_finite": distribution(values("probe_latency_ms")),
        "abs_midpoint_offset_ms_valid_intervals": distribution(values("raw_offset_ms", True, True)),
        "half_interval_uncertainty_ms_valid_intervals": distribution(values("offset_uncertainty_ms", False, True)),
        "abs_interval_residual_ms_valid_intervals": distribution(values("offset_ms", True, True)),
        "probe_latency_ms_valid_intervals": distribution(values("probe_latency_ms", False, True)),
    }
    return {
        "run": run, "host_role": role, "probe_rows": len(rows),
        "health_records": len(health_samples),
        "available_n": sum(r["available"] for r in rows),
        "available_fraction": sum(r["available"] for r in rows) / len(rows) if rows else None,
        "missing_probe_n": groups.get("missing_probe", 0),
        "unavailable_n": groups.get("unavailable", 0),
        "invalid_n": sum(n for name, n in groups.items() if name.startswith("invalid_")),
        "valid_interval_n": groups.get("valid_probe_interval", 0),
        "reference_only_n": groups.get("reference_only", 0),
        "validity_counts": dict(sorted(groups.items())),
        "formula_checked_n": sum(r["formula_checked"] for r in rows),
        "formula_consistent_n": sum(r["formula_consistent"] for r in rows),
        "abs_midpoint_offset_gt_1000ms_n": sum(v > 1000 for v in values("raw_offset_ms", True)),
        "half_interval_uncertainty_gt_1000ms_n": sum(v > 1000 for v in values("offset_uncertainty_ms")),
        "abs_interval_residual_gt_1000ms_n": sum(v > 1000 for v in values("offset_ms", True)),
        "health_record_span_seconds_sum_within_runs": span,
        "health_interval_seconds": distribution(gaps),
        "health_interval_gt_60s_n": sum(gap > 60 for gap in gaps),
        "health_interval_excess_over_60s_total": sum(max(0, gap - 60) for gap in gaps),
        "health_timestamp_reversals_n": reversals,
        "health_timestamp_duplicates_n": duplicates,
        "health_timestamp_invalid_n": invalid_timestamps,
        "first_health_timestamp_utc": min((r["timestamp_utc"] for r in rows), default=None),
        "last_health_timestamp_utc": max((r["timestamp_utc"] for r in rows), default=None),
        "metrics": metrics,
    }


def core_reference_counts(rows):
    counts = []
    for run in sorted(set(r["run"] for r in rows)):
        core = [r for r in rows if r["run"] == run and r["host_role"] == "core"]
        counts.append({
            "run": run, "host_role": "core", "probe_rows": len(core),
            "available_n": sum(r["available"] for r in core),
            "missing_probe_n": sum(not r["probe_present"] for r in core),
            "nonzero_offset_n": sum(r["offset_ms"] not in (None, 0) for r in core),
            "missing_offset_n": sum(r["offset_ms"] is None for r in core),
            "nonzero_latency_n": sum(r["probe_latency_ms"] not in (None, 0) for r in core),
        })
    return counts


def summary(rows, core_counts):
    result = []
    for run in sorted(set(r["run"] for r in rows)):
        for role in REMOTE_ROLES:
            result.append(summarize_group([
                r for r in rows if r["run"] == run and r["host_role"] == role
            ], run, role))
    for role in REMOTE_ROLES + ("remote_combined",):
        result.append(summarize_group([
            r for r in rows if r["host_role"] == role or (
                role == "remote_combined" and r["host_role"] != "core"
            )
        ], "ALL_W1", role))
    health = [r for r in rows if r["host_role"] == "ran"]
    return {
        "schema": "w1_clock_quality_v1", "units": "milliseconds unless named seconds",
        "scope": "seven accepted W1 runs only; pooled remote distributions exclude core reference",
        "quantile": "linear interpolation at (n-1)*p; medians are unweighted per probe",
        "finite_value_policy": "all finite values retained including invalid or extreme probes; valid-interval bound is additionally labelled",
        "health_interval_scope": "between health-record timestamps within each run; gaps between different runs excluded; 60 seconds is a descriptive threshold, not an acceptance gate",
        "uncertainty_boundary": "midpoint offsets and SSH interval widths are probe observations, not measured cross-host event alignment errors; interval bounds assume a forward local interval and clocks stable within each probe",
        "record_clock_skew_ms_all_finite": distribution([
            r["record_clock_skew_ms"] for r in health
        ]),
        "record_clock_skew_gt_1000ms_n": sum(
            r["record_clock_skew_ms"] is not None and r["record_clock_skew_ms"] > 1000
            for r in health
        ),
        "core_reference_counts": core_counts,
        "groups": result,
    }


def check(rows, core_counts):
    assert producer(1100, 1000, 1200) == (0, 100, 0, 200, 200)
    assert producer(1250, 1000, 1200) == (150, 100, 50, 200, 200)
    assert producer(950, 1000, 1200) == (-150, 100, -50, 200, 200)
    assert producer(1100, 1200, 1000) == (0, 0, -100, 0, -200)
    assert quantile([1, 2, 3, 4], 0.95) == 3.8499999999999996
    assert distribution([]) == {"n": 0, "median": None, "p95": None, "max": None}
    assert set(r["run"] for r in rows) == {"W1-D%02d" % d for d in range(1, 8)}
    assert all(r["host_role"] in REMOTE_ROLES for r in rows)
    core_by_run = {r["run"]: r for r in core_counts}
    keys = [(r["run"], r["host_role"], r["sample_index"]) for r in rows]
    assert len(keys) == len(set(keys))
    paired = {}
    record_offsets = {}
    for row in rows:
        key = (row["run"], row["sample_index"])
        signature = (row["timestamp_utc"], row["record_clock_skew_ms"])
        if key in paired:
            assert paired[key] == signature
        paired[key] = signature
        record_offsets.setdefault(key, []).append(row)
    for key, probes in record_offsets.items():
        if len(probes) == 2 and all(not r["available"] or r["offset_ms"] is not None for r in probes):
            offsets = [0] + [r["offset_ms"] for r in probes if r["available"]]
            actual = paired[key][1]
            if actual is not None:
                assert abs(actual - (max(offsets) - min(offsets))) <= 0.001
    for run in set(r["run"] for r in rows):
        counts = [sum(r["run"] == run and r["host_role"] == role for r in rows) for role in REMOTE_ROLES]
        assert counts[0] == counts[1] == core_by_run[run]["probe_rows"]
        indices = [{r["sample_index"] for r in rows if r["run"] == run and r["host_role"] == role} for role in REMOTE_ROLES]
        assert indices[0] == indices[1]
    for row in rows:
        if row["validity"] == "valid_probe_interval":
            raw, uncertainty = row["raw_offset_ms"], row["offset_uncertainty_ms"]
            expected = math.copysign(max(0, abs(raw) - uncertainty), raw)
            assert abs(expected - row["offset_ms"]) <= 0.001
            assert row["available"] and row["formula_checked"] and row["formula_consistent"]
    for group in summary(rows, core_counts)["groups"]:
        assert sum(group["validity_counts"].values()) == group["probe_rows"]
        if group["host_role"] != "core":
            assert (group["valid_interval_n"] + group["invalid_n"] + group["missing_probe_n"] + group["unavailable_n"]) == group["probe_rows"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    directory = Path(__file__).resolve().parents[1] / "platform_data" / "quality" / "clock"
    parser.add_argument("--evidence", type=Path, default=directory, help="directory containing the seven per-run evidence CSVs and core-reference counts")
    parser.add_argument("--output-dir", type=Path, default=directory)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--check", action="store_true", help="also verify formulas, quantiles and denominator conservation")
    args = parser.parse_args()
    if bool(args.run_root) != bool(args.registry):
        parser.error("--run-root and --registry must be provided together")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.run_root:
        extracted = list(extract(args.run_root, args.registry))
        core_counts = core_reference_counts(extracted)
        rows = [r for r in extracted if r["host_role"] != "core"]
        for run in sorted(set(r["run"] for r in rows)):
            write_csv(args.output_dir / ("clock_evidence_" + run + ".csv"),
                      [r for r in rows if r["run"] == run], FIELDS)
        (args.output_dir / "clock_core_reference_counts.json").write_text(
            json.dumps(core_counts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    else:
        rows = list(read_evidence(args.evidence))
        evidence_dir = args.evidence if args.evidence.is_dir() else args.evidence.parent
        core_counts = json.loads((evidence_dir / "clock_core_reference_counts.json").read_text(encoding="utf-8"))
    if args.check:
        check(rows, core_counts)
    write_csv(args.output_dir / "clock_flagged_probes.csv", [
        r for r in rows if r["flags"] or r["validity"] != "valid_probe_interval"
    ], FIELDS)
    result = summary(rows, core_counts)
    (args.output_dir / "clock_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    flattened = []
    for group in result["groups"]:
        row = {k: v for k, v in group.items() if k not in ("metrics", "validity_counts", "health_interval_seconds")}
        for metric, stats in group["metrics"].items():
            row.update({metric + "_" + k: v for k, v in stats.items()})
        row.update({"health_interval_seconds_" + k: v for k, v in group["health_interval_seconds"].items()})
        flattened.append(row)
    write_csv(args.output_dir / "clock_summary.csv", flattened, list(flattened[0]))
    print(json.dumps({"probe_rows": len(rows), "summary_groups": len(result["groups"]), "checks_passed": args.check}, sort_keys=True))


if __name__ == "__main__":
    main()
